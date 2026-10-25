# SmartSpend

SmartSpend is a personal finance analytics platform for tracking expenses, monthly budgets, analytics, alerts, and savings goals.

## Overview

- Expense service: stores and queries expense transactions.
- Budget service: stores monthly overall budgets and category budgets.
- Analytics service: aggregates spending by day, month, and category for dashboards.
- Alert service: computes budget-threshold notifications.
- Savings service: tracks a savings ledger, explicit allocations, and goal progress.
- Frontend: React + Vite dashboard built with reusable cards and Recharts visualizations.

## Architecture

- Frontend: React in `frontend/`
- Backend services: `services/*/app/main.py`
- Databases: SQLite by default for local development; PostgreSQL is the preferred production target for structured financial data.
- Containers: Docker Compose service orchestration via `docker-compose.yml`

## Local setup

1. Install Python dependencies:
   `python -m pip install -r requirements.txt`
2. Install frontend dependencies:
   `cd frontend && npm install`
3. Copy environment variables:
   `cp .env.example .env` (or create equivalent Windows env vars in your shell)
4. Start all services:
   `docker compose up --build`
   or run each FastAPI service individually with `uvicorn app.main:app --reload --port <port>`.
5. Run the frontend:
   `cd frontend && npm run dev -- --host 0.0.0.0 --port 5173`

## Service endpoints

- Expense service: `http://127.0.0.1:8000`
- Budget service: `http://127.0.0.1:8001`
- Analytics service: `http://127.0.0.1:8002`
- Alert service: `http://127.0.0.1:8003`
- Savings service: `http://127.0.0.1:8004`
- Frontend: `http://127.0.0.1:5173`

## Feature notes

- Monthly budgets are saved by `YYYY-MM` and require a unique month.
- Budget creation and updates are explicit operations; no default ₹20,000 budget is injected silently.
- Savings balance is driven by ledger transactions only; budget remaining and savings allocation are separate values.
- The analytics dashboard reads real backend data and shows empty/loading/error states.

## Testing

Run the Python suite:
`python -m pytest -q`

Run the frontend build:
`cd frontend && npm run build`

## Seed data

To create local sample data:
`python scripts/seed_sample_data.py`

## Migration and production guidance

- Existing SQLite databases are preserved and not overwritten.
- For production, move to PostgreSQL and use SQLAlchemy/Alembic migrations.
- Keep environment variables outside version control; do not commit secrets.
- If you need a database backup before a migration, copy the `.db` files in each `services/*/data` folder to a timestamped backup directory.

## Deployment

- Docker Compose is configured for local containerized testing.
- GitHub Actions can be layered on top for CI, linting, and test automation.
- The project is not yet using a full PostgreSQL migration stack in code, but the service architecture is structured to support it.

