from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPENSE_DB = ROOT / 'services' / 'expense-service' / 'data' / 'expenses.db'
BUDGET_DB = ROOT / 'services' / 'budget-service' / 'data' / 'budgets.db'
SAVINGS_DB = ROOT / 'services' / 'savings-service' / 'data' / 'savings.db'


def ensure_db(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.close()


def seed_expenses():
    ensure_db(EXPENSE_DB)
    conn = sqlite3.connect(EXPENSE_DB)
    conn.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, description TEXT NOT NULL, amount REAL NOT NULL CHECK(amount > 0), category TEXT NOT NULL, date TEXT NOT NULL)')
    conn.execute('DELETE FROM expenses')
    rows = [
        ('Groceries', 2400, 'Food', '2026-10-02'),
        ('Metro pass', 700, 'Transport', '2026-10-04'),
        ('Electricity bill', 3200, 'Bills', '2026-10-06'),
        ('Phone repair', 1500, 'Healthcare', '2026-10-12'),
        ('Laptop bag', 4200, 'Shopping', '2026-10-14'),
    ]
    conn.executemany('INSERT INTO expenses (description, amount, category, date) VALUES (?, ?, ?, ?)', rows)
    conn.commit()
    conn.close()


def seed_budget():
    ensure_db(BUDGET_DB)
    conn = sqlite3.connect(BUDGET_DB)
    conn.execute('CREATE TABLE IF NOT EXISTS monthly_budgets (id INTEGER PRIMARY KEY AUTOINCREMENT, month TEXT NOT NULL UNIQUE, amount REAL NOT NULL CHECK(amount > 0), created_at TEXT NOT NULL DEFAULT (datetime("now")), updated_at TEXT NOT NULL DEFAULT (datetime("now")))')
    conn.execute('CREATE TABLE IF NOT EXISTS budgets (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, monthly_limit REAL NOT NULL CHECK(monthly_limit > 0), month TEXT NOT NULL, UNIQUE(category, month))')
    conn.execute('DELETE FROM monthly_budgets')
    conn.execute('DELETE FROM budgets')
    conn.execute('INSERT INTO monthly_budgets (month, amount, created_at, updated_at) VALUES (?, ?, datetime("now"), datetime("now"))', ('2026-10', 30000))
    conn.execute('INSERT INTO budgets (category, monthly_limit, month) VALUES (?, ?, ?)', ('Food', 9000, '2026-10'))
    conn.execute('INSERT INTO budgets (category, monthly_limit, month) VALUES (?, ?, ?)', ('Bills', 11000, '2026-10'))
    conn.commit() 
    conn.close()


def seed_savings():
    ensure_db(SAVINGS_DB)
    conn = sqlite3.connect(SAVINGS_DB)
    conn.execute('CREATE TABLE IF NOT EXISTS savings_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL CHECK(type IN ("deposit","withdrawal","goal_contribution","goal_withdrawal")), amount REAL NOT NULL CHECK(amount > 0), note TEXT, idempotency_key TEXT UNIQUE, goal_id INTEGER REFERENCES savings_goals(id), created_at TEXT NOT NULL DEFAULT (datetime("now")))')
    conn.execute('CREATE TABLE IF NOT EXISTS savings_goals (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, target_amount REAL NOT NULL CHECK(target_amount > 0), current_amount REAL NOT NULL DEFAULT 0 CHECK(current_amount >= 0), target_date TEXT, created_at TEXT NOT NULL DEFAULT (datetime("now")), updated_at TEXT NOT NULL DEFAULT (datetime("now")))')
    conn.execute('CREATE TABLE IF NOT EXISTS savings_allocations (id INTEGER PRIMARY KEY AUTOINCREMENT, month TEXT NOT NULL, amount REAL NOT NULL CHECK(amount > 0), note TEXT, idempotency_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT (datetime("now")))')
    conn.execute('DELETE FROM savings_ledger')
    conn.execute('DELETE FROM savings_goals')
    conn.execute('DELETE FROM savings_allocations')
    conn.execute('INSERT INTO savings_ledger (type, amount, note, idempotency_key, created_at) VALUES (?, ?, ?, ?, datetime("now"))', ('deposit', 10000, 'Initial balance', 'seed-savings-deposit'))
    conn.execute('INSERT INTO savings_goals (name, target_amount, current_amount, target_date, created_at, updated_at) VALUES (?, ?, ?, ?, datetime("now"), datetime("now"))', ('Laptop', 80000, 5000, '2026-12-30'))
    conn.commit()
    conn.close()


if __name__ == '__main__':
    seed_expenses()
    seed_budget()
    seed_savings()
    print('Seeded SmartSpend sample data.')
