import os

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

EXPENSE_SERVICE_URL = os.environ.get("EXPENSE_SERVICE_URL", "http://127.0.0.1:8000").rstrip("/")
BUDGET_SERVICE_URL = os.environ.get("BUDGET_SERVICE_URL", "http://127.0.0.1:8001").rstrip("/")

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://localhost:3000",
    ).split(",")
    if o.strip()
]

HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "10"))


app = FastAPI(
    title="SmartSpend Alert Service",
    description="Generate spending and budget threshold alerts",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def _get_json(url: str, params: dict | None = None):
    """GET a JSON response; returns None on 404, raises HTTPException on errors."""
    try:
        response = httpx.get(url, params=params, timeout=HTTP_TIMEOUT)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504, detail=f"Upstream service timed out ({url})"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream service error HTTP {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503, detail=f"Service unavailable: {url}"
        ) from exc


def _reachable(url: str) -> bool:
    try:
        return httpx.get(url, timeout=5).status_code == 200
    except httpx.RequestError:
        return False


# ── Root / Health ────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "alert-service", "status": "running"}


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "alert-service",
        "expense_service_reachable": _reachable(f"{EXPENSE_SERVICE_URL}/health"),
        "budget_service_reachable": _reachable(f"{BUDGET_SERVICE_URL}/health"),
    }


# ── Alerts ───────────────────────────────────────────────────────────────────

@app.get("/alerts")
def get_alerts(
    month: str = Query(
        ...,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Month in YYYY-MM format, e.g. 2026-10",
    )
):
    # Fetch per-category budgets for this month
    category_budgets = _get_json(
        f"{BUDGET_SERVICE_URL}/budgets", params={"month": month}
    ) or []

    # Fetch overall monthly budget (None if not set)
    overall_budget = _get_json(f"{BUDGET_SERVICE_URL}/monthly-budgets/{month}")

    # Fetch all expenses for this month
    expenses = _get_json(
        f"{EXPENSE_SERVICE_URL}/expenses",
        params={"month": month, "limit": 2000},
    ) or []

    # Aggregate spending
    spending_by_category: dict[str, float] = {}
    total_spending = 0.0
    for expense in expenses:
        cat = expense["category"].strip().casefold()
        spending_by_category[cat] = spending_by_category.get(cat, 0.0) + expense["amount"]
        total_spending += expense["amount"]

    alerts = []

    # Overall budget alert (prepended so it appears first)
    if overall_budget and isinstance(overall_budget, dict):
        overall_limit = overall_budget["amount"]
        pct = (total_spending / overall_limit * 100) if overall_limit else 0.0

        if pct >= 80:
            severity = "critical" if pct >= 100 else "warning"
            if pct >= 100:
                msg = "Overall monthly budget exceeded" if pct > 100 else "Overall monthly budget fully used"
            else:
                msg = "Overall spending has reached at least 80% of the monthly budget"

            alerts.append({
                "type": "overall",
                "category": None,
                "month": month,
                "budget": overall_limit,
                "spent": round(total_spending, 2),
                "remaining": round(overall_limit - total_spending, 2),
                "percentage_used": round(pct, 2),
                "severity": severity,
                "message": msg,
            })

    # Per-category alerts
    for budget in category_budgets:
        category = budget["category"]
        limit = budget["monthly_limit"]
        spent = spending_by_category.get(category.strip().casefold(), 0.0)
        pct = (spent / limit * 100) if limit else 0.0

        if pct < 80:
            continue

        severity = "critical" if pct >= 100 else "warning"
        if pct >= 100:
            msg = "Budget exceeded" if pct > 100 else "Budget fully used"
        else:
            msg = "Spending has reached at least 80% of the budget"

        alerts.append({
            "type": "category",
            "category": category,
            "month": month,
            "budget": limit,
            "spent": round(spent, 2),
            "remaining": round(limit - spent, 2),
            "percentage_used": round(pct, 2),
            "severity": severity,
            "message": msg,
        })

    return {
        "month": month,
        "alert_count": len(alerts),
        "alerts": alerts,
    }
