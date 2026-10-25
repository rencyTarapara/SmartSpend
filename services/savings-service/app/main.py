from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
import os
import sqlite3
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(
    os.environ.get("SMARTSPEND_SAVINGS_DB", str(DATA_DIR / "savings.db"))
)
EXPENSE_SERVICE_URL = os.environ.get(
    "EXPENSE_SERVICE_URL", "http://127.0.0.1:8000"
).rstrip("/")
BUDGET_SERVICE_URL = os.environ.get(
    "BUDGET_SERVICE_URL", "http://127.0.0.1:8001"
).rstrip("/")
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "10"))

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://localhost:3000",
    ).split(",")
    if o.strip()
]

# ── Accounting rules ──────────────────────────────────────────────────────────
# (1) Monthly budget remaining  = overall_budget.amount - sum(expenses for month)
#     This is tracked by budget-service + expense-service, NOT here.
# (2) Savings balance           = sum(deposits + goal_withdrawals)
#                               - sum(withdrawals + goal_contributions)
#     Computed from savings_ledger — a single source of truth.
# (3) Savings goals             = sub-allocations of the savings balance.
#     Contributing to a goal reduces the free savings balance.
#     The same money is NEVER counted as both an expense and a saving.
# ─────────────────────────────────────────────────────────────────────────────


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize_database():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS savings_goals (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL,
                target_amount REAL    NOT NULL CHECK(target_amount > 0),
                current_amount REAL   NOT NULL DEFAULT 0 CHECK(current_amount >= 0),
                target_date   TEXT,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS savings_ledger (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                type             TEXT    NOT NULL
                                         CHECK(type IN (
                                             'deposit',
                                             'withdrawal',
                                             'goal_contribution',
                                             'goal_withdrawal'
                                         )),
                amount           REAL    NOT NULL CHECK(amount > 0),
                note             TEXT,
                idempotency_key  TEXT    UNIQUE,
                goal_id          INTEGER REFERENCES savings_goals(id),
                created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS savings_allocations (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                month            TEXT    NOT NULL,
                amount           REAL    NOT NULL CHECK(amount > 0),
                note             TEXT,
                idempotency_key  TEXT    NOT NULL UNIQUE,
                created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ledger_created ON savings_ledger(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_savings_allocations_month ON savings_allocations(month)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_savings_allocations_created ON savings_allocations(created_at)"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="SmartSpend Savings Service",
    description="Manage savings balance, ledger and goals",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _balance(conn) -> float:
    row = conn.execute("""
        SELECT
          COALESCE(SUM(CASE WHEN type IN ('deposit','goal_withdrawal')   THEN amount ELSE 0 END), 0)
          - COALESCE(SUM(CASE WHEN type IN ('withdrawal','goal_contribution') THEN amount ELSE 0 END), 0)
          AS balance
        FROM savings_ledger
    """).fetchone()
    allocated = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM savings_allocations"
    ).fetchone()[0]
    return round(float(row["balance"]) + float(allocated), 2)


def _check_idempotency(conn, key: str, expected_type: str, amount: float):
    if conn.execute(
        "SELECT 1 FROM savings_allocations WHERE idempotency_key = ?", (key,)
    ).fetchone():
        raise HTTPException(
            status_code=409,
            detail="Idempotency key was already used for a different transaction",
        )
    existing = conn.execute(
        "SELECT * FROM savings_ledger WHERE idempotency_key = ?", (key,)
    ).fetchone()
    if existing is not None:
        if existing["type"] != expected_type or existing["amount"] != amount:
            raise HTTPException(
                status_code=409,
                detail="Idempotency key was already used for a different transaction",
            )
        return existing
    return None


def _budget_and_spending(month: str) -> tuple[float, float]:
    try:
        budget_response = httpx.get(
            f"{BUDGET_SERVICE_URL}/monthly-budgets/{month}",
            timeout=HTTP_TIMEOUT,
        )
        if budget_response.status_code == 404:
            raise HTTPException(
                status_code=422,
                detail=f"No monthly budget is set for {month}",
            )
        budget_response.raise_for_status()
        budget_amount = float(budget_response.json()["amount"])

        expenses = []
        offset = 0
        while True:
            response = httpx.get(
                f"{EXPENSE_SERVICE_URL}/expenses",
                params={"month": month, "limit": 2000, "offset": offset},
                timeout=HTTP_TIMEOUT,
            )
            response.raise_for_status()
            page = response.json()
            expenses.extend(page)
            if len(page) < 2000:
                break
            offset += 2000
        spent = sum(float(expense["amount"]) for expense in expenses)
        return budget_amount, spent
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="A finance service timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"A finance service returned HTTP {exc.response.status_code}",
        ) from exc
    except (httpx.RequestError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=503, detail="Could not retrieve the budget and expenses"
        ) from exc


def _ledger_dict(row) -> dict:
    return {
        "id": row["id"],
        "type": row["type"],
        "amount": row["amount"],
        "note": row["note"],
        "idempotency_key": row["idempotency_key"],
        "goal_id": row["goal_id"],
        "created_at": row["created_at"],
    }


def _goal_dict(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "target_amount": row["target_amount"],
        "current_amount": row["current_amount"],
        "target_date": row["target_date"],
        "progress_pct": round(
            (row["current_amount"] / row["target_amount"]) * 100, 2
        ) if row["target_amount"] else 0.0,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ── Request models ────────────────────────────────────────────────────────────

class DepositRequest(BaseModel):
    amount: float = Field(gt=0, allow_inf_nan=False, description="Amount to deposit into savings")
    note: str | None = Field(default=None, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=100)


class WithdrawalRequest(BaseModel):
    amount: float = Field(gt=0, allow_inf_nan=False, description="Amount to withdraw from savings")
    note: str | None = Field(default=None, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=100)


class GoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    target_amount: float = Field(gt=0, allow_inf_nan=False)
    target_date: date | None = None


class GoalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    target_amount: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    target_date: date | None = None


class ContributionRequest(BaseModel):
    amount: float = Field(gt=0, allow_inf_nan=False)
    note: str | None = Field(default=None, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=100)


class AllocationRequest(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount: float = Field(gt=0, allow_inf_nan=False)
    note: str | None = Field(default=None, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=100)


# ── Root / Health ─────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "savings-service", "status": "running"}


@app.get("/health")
def health():
    return {"status": "healthy", "service": "savings-service"}


# ── Balance ───────────────────────────────────────────────────────────────────

@app.get("/savings/balance")
def get_balance():
    with get_connection() as conn:
        balance = _balance(conn)
        count = conn.execute("SELECT COUNT(*) FROM savings_ledger").fetchone()[0]
    return {"balance": balance, "transaction_count": count}


# ── Deposit ───────────────────────────────────────────────────────────────────

@app.post("/savings/deposit", status_code=201)
def deposit(payload: DepositRequest):
    key = payload.idempotency_key or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = _check_idempotency(conn, key, "deposit", payload.amount)
        if existing:
            return {**_ledger_dict(existing), "balance_after": _balance(conn), "idempotent": True}

        cursor = conn.execute(
            "INSERT INTO savings_ledger (type, amount, note, idempotency_key, created_at) VALUES (?,?,?,?,?)",
            ("deposit", payload.amount, payload.note, key, now),
        )
        row = conn.execute(
            "SELECT * FROM savings_ledger WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return {**_ledger_dict(row), "balance_after": _balance(conn)}


# ── Withdrawal ────────────────────────────────────────────────────────────────

@app.post("/savings/withdraw", status_code=201)
def withdraw(payload: WithdrawalRequest):
    key = payload.idempotency_key or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = _check_idempotency(conn, key, "withdrawal", payload.amount)
        if existing:
            return {**_ledger_dict(existing), "balance_after": _balance(conn), "idempotent": True}

        balance = _balance(conn)
        if payload.amount > balance:
            raise HTTPException(
                status_code=422,
                detail=f"Insufficient balance. Available: ₹{balance:.2f}, requested: ₹{payload.amount:.2f}",
            )

        cursor = conn.execute(
            "INSERT INTO savings_ledger (type, amount, note, idempotency_key, created_at) VALUES (?,?,?,?,?)",
            ("withdrawal", payload.amount, payload.note, key, now),
        )
        row = conn.execute(
            "SELECT * FROM savings_ledger WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return {**_ledger_dict(row), "balance_after": _balance(conn)}


@app.get("/savings/allocations")
def list_allocations(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
):
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM savings_allocations WHERE month = ?",
            (month,),
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM savings_allocations WHERE month = ? ORDER BY created_at DESC, id DESC",
            (month,),
        ).fetchall()
    return {
        "month": month,
        "allocated": round(total, 2),
        "allocations": [
            {
                "id": row["id"],
                "type": "allocation",
                "month": row["month"],
                "amount": row["amount"],
                "note": row["note"],
                "idempotency_key": row["idempotency_key"],
                "created_at": row["created_at"],
            }
            for row in rows
        ],
    }


@app.post("/savings/allocate", status_code=201)
def allocate_monthly_funds(payload: AllocationRequest):
    key = payload.idempotency_key or str(uuid.uuid4())
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM savings_allocations WHERE idempotency_key = ?", (key,)
        ).fetchone()
        if existing:
            if existing["amount"] != payload.amount or existing["month"] != payload.month:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key was already used for a different allocation",
                )
            return {
                "id": existing["id"],
                "type": "allocation",
                "month": existing["month"],
                "amount": existing["amount"],
                "note": existing["note"],
                "idempotency_key": existing["idempotency_key"],
                "balance_after": _balance(conn),
                "idempotent": True,
            }
        if conn.execute(
            "SELECT 1 FROM savings_ledger WHERE idempotency_key = ?", (key,)
        ).fetchone():
            raise HTTPException(
                status_code=409,
                detail="Idempotency key was already used for a different transaction",
            )

    budget_amount, spent = _budget_and_spending(payload.month)
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM savings_allocations WHERE idempotency_key = ?", (key,)
        ).fetchone()
        if existing:
            if existing["amount"] != payload.amount or existing["month"] != payload.month:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key was already used for a different allocation",
                )
            return {
                "id": existing["id"],
                "type": "allocation",
                "month": existing["month"],
                "amount": existing["amount"],
                "note": existing["note"],
                "idempotency_key": existing["idempotency_key"],
                "balance_after": _balance(conn),
                "idempotent": True,
            }

        allocated = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM savings_allocations WHERE month = ?",
            (payload.month,),
        ).fetchone()[0]
        available = round(budget_amount - spent - allocated, 2)
        if payload.amount > available:
            raise HTTPException(
                status_code=422,
                detail=f"Insufficient unallocated funds for {payload.month}. Available: ₹{max(available, 0):.2f}",
            )

        cursor = conn.execute(
            """INSERT INTO savings_allocations
               (month, amount, note, idempotency_key, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (payload.month, payload.amount, payload.note, key, now),
        )
        row = conn.execute(
            "SELECT * FROM savings_allocations WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return {
            "id": row["id"],
            "type": "allocation",
            "month": row["month"],
            "amount": row["amount"],
            "note": row["note"],
            "idempotency_key": row["idempotency_key"],
            "balance_after": _balance(conn),
            "available_after": round(available - payload.amount, 2),
        }


# ── Ledger history ────────────────────────────────────────────────────────────

@app.get("/savings/transactions")
def list_transactions(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM savings_ledger ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        ledger_total = conn.execute("SELECT COUNT(*) FROM savings_ledger").fetchone()[0]
        allocation_total = conn.execute(
            "SELECT COUNT(*) FROM savings_allocations"
        ).fetchone()[0]
        allocation_rows = conn.execute(
            """SELECT id, month, amount, note, idempotency_key, created_at
               FROM savings_allocations ORDER BY created_at DESC, id DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
        balance = _balance(conn)
    transactions = [_ledger_dict(row) for row in rows]
    transactions.extend(
        {
            "id": row["id"],
            "type": "allocation",
            "month": row["month"],
            "amount": row["amount"],
            "note": row["note"],
            "idempotency_key": row["idempotency_key"],
            "goal_id": None,
            "created_at": row["created_at"],
        }
        for row in allocation_rows
    )
    transactions.sort(key=lambda item: item["created_at"], reverse=True)
    transactions = transactions[offset : offset + limit]
    return {
        "balance": balance,
        "total": ledger_total + allocation_total,
        "transactions": transactions,
    }


# ── Goals ─────────────────────────────────────────────────────────────────────

@app.post("/savings/goals", status_code=201)
def create_goal(payload: GoalCreate):
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO savings_goals (name, target_amount, target_date, created_at, updated_at) VALUES (?,?,?,?,?)",
            (
                payload.name.strip(),
                payload.target_amount,
                payload.target_date.isoformat() if payload.target_date else None,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM savings_goals WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return _goal_dict(row)


@app.get("/savings/goals")
def list_goals():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM savings_goals ORDER BY created_at DESC"
        ).fetchall()
    return [_goal_dict(r) for r in rows]


@app.get("/savings/goals/{goal_id}")
def get_goal(goal_id: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM savings_goals WHERE id = ?", (goal_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Savings goal not found")
    return _goal_dict(row)


@app.put("/savings/goals/{goal_id}")
def update_goal(goal_id: int, payload: GoalUpdate):
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM savings_goals WHERE id = ?", (goal_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Savings goal not found")

        new_name = payload.name.strip() if payload.name else existing["name"]
        new_target = payload.target_amount if payload.target_amount else existing["target_amount"]
        new_date = (
            payload.target_date.isoformat()
            if payload.target_date is not None
            else existing["target_date"]
        )

        conn.execute(
            "UPDATE savings_goals SET name=?, target_amount=?, target_date=?, updated_at=? WHERE id=?",
            (new_name, new_target, new_date, now, goal_id),
        )
        row = conn.execute(
            "SELECT * FROM savings_goals WHERE id = ?", (goal_id,)
        ).fetchone()
    return _goal_dict(row)


@app.post("/savings/goals/{goal_id}/contribute", status_code=201)
def contribute_to_goal(goal_id: int, payload: ContributionRequest):
    key = payload.idempotency_key or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = _check_idempotency(
            conn, key, "goal_contribution", payload.amount
        )
        if existing:
            if existing["goal_id"] != goal_id:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key was already used for a different goal",
                )
            return {**_ledger_dict(existing), "balance_after": _balance(conn), "idempotent": True}

        goal = conn.execute(
            "SELECT * FROM savings_goals WHERE id = ?", (goal_id,)
        ).fetchone()
        if goal is None:
            raise HTTPException(status_code=404, detail="Savings goal not found")

        balance = _balance(conn)
        if payload.amount > balance:
            raise HTTPException(
                status_code=422,
                detail=f"Insufficient balance. Available: ₹{balance:.2f}, requested: ₹{payload.amount:.2f}",
            )

        cursor = conn.execute(
            "INSERT INTO savings_ledger (type, amount, note, idempotency_key, goal_id, created_at) VALUES (?,?,?,?,?,?)",
            ("goal_contribution", payload.amount, payload.note, key, goal_id, now),
        )
        conn.execute(
            "UPDATE savings_goals SET current_amount = current_amount + ?, updated_at = ? WHERE id = ?",
            (payload.amount, now, goal_id),
        )
        ledger_row = conn.execute(
            "SELECT * FROM savings_ledger WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        updated_goal = conn.execute(
            "SELECT * FROM savings_goals WHERE id = ?", (goal_id,)
        ).fetchone()
        balance_after = _balance(conn)

    return {
        **_ledger_dict(ledger_row),
        "balance_after": balance_after,
        "goal": _goal_dict(updated_goal),
    }


@app.post("/savings/goals/{goal_id}/withdraw", status_code=201)
def withdraw_from_goal(goal_id: int, payload: ContributionRequest):
    key = payload.idempotency_key or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = _check_idempotency(conn, key, "goal_withdrawal", payload.amount)
        if existing:
            if existing["goal_id"] != goal_id:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key was already used for a different goal",
                )
            return {**_ledger_dict(existing), "balance_after": _balance(conn), "idempotent": True}

        goal = conn.execute(
            "SELECT * FROM savings_goals WHERE id = ?", (goal_id,)
        ).fetchone()
        if goal is None:
            raise HTTPException(status_code=404, detail="Savings goal not found")
        if payload.amount > goal["current_amount"]:
            raise HTTPException(
                status_code=422,
                detail=f"Insufficient goal contribution. Available: ₹{goal['current_amount']:.2f}",
            )

        cursor = conn.execute(
            """INSERT INTO savings_ledger
               (type, amount, note, idempotency_key, goal_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("goal_withdrawal", payload.amount, payload.note, key, goal_id, now),
        )
        conn.execute(
            """UPDATE savings_goals
               SET current_amount = current_amount - ?, updated_at = ?
               WHERE id = ?""",
            (payload.amount, now, goal_id),
        )
        ledger_row = conn.execute(
            "SELECT * FROM savings_ledger WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        updated_goal = conn.execute(
            "SELECT * FROM savings_goals WHERE id = ?", (goal_id,)
        ).fetchone()
        balance_after = _balance(conn)

    return {
        **_ledger_dict(ledger_row),
        "balance_after": balance_after,
        "goal": _goal_dict(updated_goal),
    }


@app.delete("/savings/goals/{goal_id}")
def delete_goal(goal_id: int):
    with get_connection() as conn:
        if conn.execute(
            "SELECT 1 FROM savings_ledger WHERE goal_id = ? LIMIT 1", (goal_id,)
        ).fetchone():
            raise HTTPException(
                status_code=409,
                detail="Savings goals with financial history cannot be deleted",
            )
        cursor = conn.execute(
            "DELETE FROM savings_goals WHERE id = ?", (goal_id,)
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Savings goal not found")
    return {"message": "Savings goal deleted", "id": goal_id}
