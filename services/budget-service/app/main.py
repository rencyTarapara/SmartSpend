from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "budgets.db"

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://localhost:3000",
    ).split(",")
    if o.strip()
]

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_connection() as connection:
        # Per-category budgets (existing table, preserved)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                monthly_limit REAL NOT NULL CHECK(monthly_limit > 0),
                month TEXT NOT NULL,
                UNIQUE(category, month)
            )
        """)
        # Overall monthly budgets (new)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS monthly_budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL UNIQUE,
                amount REAL NOT NULL CHECK(amount > 0),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_budgets_month ON budgets(month)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_monthly_budgets_month ON monthly_budgets(month)"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="SmartSpend Budget Service",
    description="Manage per-category and overall monthly spending budgets",
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


# ── Category Budget Models ──────────────────────────────────────────────────

class BudgetCreate(BaseModel):
    category: str = Field(min_length=1, max_length=50)
    monthly_limit: float = Field(gt=0, allow_inf_nan=False)
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


def budget_to_dict(row):
    return {
        "id": row["id"],
        "category": row["category"],
        "monthly_limit": row["monthly_limit"],
        "month": row["month"],
    }


# ── Overall Monthly Budget Models ───────────────────────────────────────────

class MonthlyBudgetCreate(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount: float = Field(gt=0, allow_inf_nan=False)


class MonthlyBudgetUpdate(BaseModel):
    amount: float = Field(gt=0, allow_inf_nan=False)


def monthly_budget_to_dict(row):
    return {
        "id": row["id"],
        "month": row["month"],
        "amount": row["amount"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ── Root / Health ───────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "budget-service", "status": "running"}


@app.get("/health")
def health():
    return {"status": "healthy", "service": "budget-service"}


# ── Category Budget Endpoints ───────────────────────────────────────────────

@app.post("/budgets", status_code=201)
def create_budget(budget: BudgetCreate):
    category = budget.category.strip()
    try:
        with get_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO budgets (category, monthly_limit, month) VALUES (?, ?, ?)",
                (category, budget.monthly_limit, budget.month),
            )
            row = connection.execute(
                "SELECT * FROM budgets WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return budget_to_dict(row)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="A budget for this category and month already exists",
        ) from exc


@app.get("/budgets")
def list_budgets(
    month: str | None = Query(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    )
):
    with get_connection() as connection:
        if month:
            rows = connection.execute(
                "SELECT * FROM budgets WHERE month = ? ORDER BY category",
                (month,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM budgets ORDER BY month DESC, category",
            ).fetchall()
    return [budget_to_dict(row) for row in rows]


@app.put("/budgets/{budget_id}")
def update_budget(budget_id: int, budget: BudgetCreate):
    category = budget.category.strip()
    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """UPDATE budgets
                   SET category = ?, monthly_limit = ?, month = ?
                   WHERE id = ?""",
                (category, budget.monthly_limit, budget.month, budget_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Budget not found")
            row = connection.execute(
                "SELECT * FROM budgets WHERE id = ?", (budget_id,)
            ).fetchone()
            return budget_to_dict(row)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="A budget for this category and month already exists",
        ) from exc


@app.delete("/budgets/{budget_id}")
def delete_budget(budget_id: int):
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM budgets WHERE id = ?", (budget_id,)
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Budget not found")
    return {"message": "Budget deleted successfully", "id": budget_id}


# ── Overall Monthly Budget Endpoints ────────────────────────────────────────

@app.post("/monthly-budgets", status_code=201)
def create_monthly_budget(payload: MonthlyBudgetCreate):
    now = datetime.now(timezone.utc).isoformat()
    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """INSERT INTO monthly_budgets (month, amount, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (payload.month, payload.amount, now, now),
            )
            row = connection.execute(
                "SELECT * FROM monthly_budgets WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return monthly_budget_to_dict(row)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"An overall budget for {payload.month} already exists. Use PUT /monthly-budgets/{payload.month} to update it.",
        ) from exc


@app.get("/monthly-budgets")
def list_monthly_budgets():
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM monthly_budgets ORDER BY month DESC"
        ).fetchall()
    return [monthly_budget_to_dict(row) for row in rows]


@app.get("/monthly-budgets/{month}")
def get_monthly_budget(month: str):
    if not MONTH_RE.match(month):
        raise HTTPException(status_code=422, detail="Month must be YYYY-MM format")
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM monthly_budgets WHERE month = ?", (month,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No overall budget set for {month}")
    return monthly_budget_to_dict(row)


@app.put("/monthly-budgets/{month}")
def update_monthly_budget(month: str, payload: MonthlyBudgetUpdate):
    if not MONTH_RE.match(month):
        raise HTTPException(status_code=422, detail="Month must be YYYY-MM format")
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE monthly_budgets SET amount = ?, updated_at = ? WHERE month = ?",
            (payload.amount, now, month),
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No overall budget found for {month}. Use POST /monthly-budgets to create it.",
            )
        row = connection.execute(
            "SELECT * FROM monthly_budgets WHERE month = ?", (month,)
        ).fetchone()
    return monthly_budget_to_dict(row)


@app.delete("/monthly-budgets/{month}")
def delete_monthly_budget(month: str):
    if not MONTH_RE.match(month):
        raise HTTPException(status_code=422, detail="Month must be YYYY-MM format")
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM monthly_budgets WHERE month = ?", (month,)
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"No overall budget found for {month}")
    return {"message": f"Overall budget for {month} deleted successfully"}
