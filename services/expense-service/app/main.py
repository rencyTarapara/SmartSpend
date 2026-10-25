from contextlib import asynccontextmanager
from pathlib import Path
import os
import sqlite3

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import date

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(
    os.environ.get("SMARTSPEND_TEST_DB", str(DATA_DIR / "expenses.db"))
)

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://localhost:3000",
    ).split(",")
    if o.strip()
]


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                category TEXT NOT NULL,
                date TEXT NOT NULL
            )
        """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_expenses_date_id ON expenses(date, id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="SmartSpend Expense Service",
    description="API for managing personal expenses",
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


@app.get("/")
def root():
    return {
        "message": "SmartSpend Expense Service",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }


class ExpenseCreate(BaseModel):
    description: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0, allow_inf_nan=False)
    category: str = Field(min_length=1, max_length=50)
    date: date


class ExpenseUpdate(BaseModel):
    description: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0, allow_inf_nan=False)
    category: str = Field(min_length=1, max_length=50)
    date: date


def expense_to_dict(row):
    return {
        "id": row["id"],
        "description": row["description"],
        "amount": row["amount"],
        "category": row["category"],
        "date": row["date"],
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "expense-service"}


@app.post("/expenses", status_code=201)
def create_expense(expense: ExpenseCreate):
    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO expenses (description, amount, category, date)
                VALUES (?, ?, ?, ?)
                """,
                (
                    expense.description.strip(),
                    expense.amount,
                    expense.category.strip(),
                    expense.date.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM expenses WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            return expense_to_dict(row)
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database operation failed") from exc


@app.get("/expenses")
def list_expenses(
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    month: str | None = Query(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Filter by month, e.g. 2026-10",
    ),
    year: int | None = Query(
        default=None,
        ge=2000,
        le=2100,
        description="Filter by year, e.g. 2026",
    ),
):
    sql = "SELECT * FROM expenses"
    params: list = []
    conditions: list[str] = []

    if month:
        conditions.append("substr(date, 1, 7) = ?")
        params.append(month)
    elif year:
        conditions.append("substr(date, 1, 4) = ?")
        params.append(str(year))

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_connection() as connection:
        rows = connection.execute(sql, params).fetchall()
        return [expense_to_dict(row) for row in rows]


@app.get("/expenses/{expense_id}")
def get_expense(expense_id: int):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Expense not found")

    return expense_to_dict(row)


@app.put("/expenses/{expense_id}")
def update_expense(expense_id: int, expense: ExpenseUpdate):
    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE expenses
                SET description = ?, amount = ?, category = ?, date = ?
                WHERE id = ?
                """,
                (
                    expense.description.strip(),
                    expense.amount,
                    expense.category.strip(),
                    expense.date.isoformat(),
                    expense_id,
                ),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Expense not found")
            row = connection.execute(
                "SELECT * FROM expenses WHERE id = ?", (expense_id,)
            ).fetchone()
            return expense_to_dict(row)
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Database operation failed") from exc


@app.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int):
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM expenses WHERE id = ?",
            (expense_id,),
        )

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Expense not found")

    return {"message": "Expense deleted successfully", "id": expense_id}
