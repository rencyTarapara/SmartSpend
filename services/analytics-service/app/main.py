import os
from collections import defaultdict

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

EXPENSE_SERVICE_URL = os.environ.get("EXPENSE_SERVICE_URL", "http://127.0.0.1:8000").rstrip("/")

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
    title="SmartSpend Analytics Service",
    description="Analyze personal expenses and spending trends",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Expense HTTP helper ─────────────────────────────────────────────────────

def fetch_expenses(
    month: str | None = None,
    year: int | None = None,
) -> list[dict]:
    """Fetch expenses from the Expense Service via HTTP."""
    params: dict = {"limit": 2000, "offset": 0}
    if month:
        params["month"] = month
    elif year:
        params["year"] = str(year)

    try:
        expenses = []
        while True:
            response = httpx.get(
                f"{EXPENSE_SERVICE_URL}/expenses",
                params=params,
                timeout=HTTP_TIMEOUT,
            )
            response.raise_for_status()
            page = response.json()
            expenses.extend(page)
            if len(page) < params["limit"]:
                return expenses
            params["offset"] += params["limit"]
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Expense service timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Expense service returned HTTP {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503, detail="Expense service is unavailable"
        ) from exc


# ── Root / Health ───────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "analytics-service", "status": "running"}


@app.get("/health")
def health():
    try:
        r = httpx.get(f"{EXPENSE_SERVICE_URL}/health", timeout=5)
        expense_ok = r.status_code == 200
    except httpx.RequestError:
        expense_ok = False
    return {
        "status": "healthy",
        "service": "analytics-service",
        "expense_service_reachable": expense_ok,
    }


# ── Summary ─────────────────────────────────────────────────────────────────

@app.get("/analytics/summary")
def summary(
    month: str | None = Query(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    )
):
    expenses = fetch_expenses(month=month)
    total = sum(e["amount"] for e in expenses)
    count = len(expenses)
    avg = total / count if count else 0.0
    return {
        "month": month or "all",
        "total_spending": round(total, 2),
        "transaction_count": count,
        "average_expense": round(avg, 2),
    }


# ── Categories ──────────────────────────────────────────────────────────────

@app.get("/analytics/categories")
def category_analytics(
    month: str | None = Query(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    )
):
    expenses = fetch_expenses(month=month)
    totals: dict[str, dict] = defaultdict(
        lambda: {"total_spending": 0.0, "transaction_count": 0}
    )
    for e in expenses:
        cat = e["category"]
        totals[cat]["total_spending"] += e["amount"]
        totals[cat]["transaction_count"] += 1

    categories = [
        {
            "category": cat,
            "total_spending": round(data["total_spending"], 2),
            "transaction_count": data["transaction_count"],
        }
        for cat, data in sorted(totals.items(), key=lambda x: -x[1]["total_spending"])
    ]
    return {"month": month or "all", "categories": categories}


# ── Monthly aggregation ─────────────────────────────────────────────────────

@app.get("/analytics/monthly")
def monthly_analytics():
    expenses = fetch_expenses()
    totals: dict[str, dict] = defaultdict(
        lambda: {"total_spending": 0.0, "transaction_count": 0}
    )
    for e in expenses:
        m = e["date"][:7]
        totals[m]["total_spending"] += e["amount"]
        totals[m]["transaction_count"] += 1

    monthly = [
        {
            "month": m,
            "total_spending": round(data["total_spending"], 2),
            "transaction_count": data["transaction_count"],
        }
        for m, data in sorted(totals.items())
    ]
    return {"monthly": monthly}


# ── Daily trend for a month ─────────────────────────────────────────────────

@app.get("/analytics/daily")
def daily_analytics(
    month: str = Query(
        ...,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Month in YYYY-MM format",
    )
):
    expenses = fetch_expenses(month=month)
    totals: dict[str, dict] = defaultdict(
        lambda: {"total_spending": 0.0, "transaction_count": 0, "categories": set()}
    )
    for e in expenses:
        d = e["date"]
        totals[d]["total_spending"] += e["amount"]
        totals[d]["transaction_count"] += 1
        totals[d]["categories"].add(e["category"])

    daily = [
        {
            "date": d,
            "total_spending": round(data["total_spending"], 2),
            "transaction_count": data["transaction_count"],
            "categories": sorted(data["categories"]),
            "transactions": [
                {
                    "id": e["id"],
                    "description": e["description"],
                    "amount": round(e["amount"], 2),
                    "category": e["category"],
                    "date": e["date"],
                }
                for e in expenses
                if e["date"] == d
            ],
        }
        for d, data in sorted(totals.items())
    ]
    return {"month": month, "daily": daily}


# ── Yearly aggregation ──────────────────────────────────────────────────────

@app.get("/analytics/yearly")
def yearly_analytics(
    year: int = Query(..., ge=2000, le=2100, description="Four-digit year"),
):
    expenses = fetch_expenses(year=year)

    month_names = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]

    # Initialise all 12 months to zero so empty months appear in the chart
    monthly: dict[str, dict] = {
        f"{year}-{str(m).zfill(2)}": {
            "month": f"{year}-{str(m).zfill(2)}",
            "month_name": month_names[m - 1],
            "total_spending": 0.0,
            "transaction_count": 0,
        }
        for m in range(1, 13)
    }

    for e in expenses:
        key = e["date"][:7]
        if key in monthly:
            monthly[key]["total_spending"] += e["amount"]
            monthly[key]["transaction_count"] += 1

    for entry in monthly.values():
        entry["total_spending"] = round(entry["total_spending"], 2)

    months_list = list(monthly.values())
    total_yearly = sum(e["total_spending"] for e in months_list)
    non_zero = [e for e in months_list if e["total_spending"] > 0]
    avg_monthly = total_yearly / 12
    highest = max(non_zero, key=lambda x: x["total_spending"]) if non_zero else None
    category_totals: dict[str, dict] = defaultdict(
        lambda: {"total_spending": 0.0, "transaction_count": 0}
    )
    for expense in expenses:
        category = expense["category"]
        category_totals[category]["total_spending"] += expense["amount"]
        category_totals[category]["transaction_count"] += 1

    categories = [
        {
            "category": category,
            "total_spending": round(values["total_spending"], 2),
            "transaction_count": values["transaction_count"],
        }
        for category, values in sorted(
            category_totals.items(), key=lambda item: -item[1]["total_spending"]
        )
    ]

    return {
        "year": year,
        "months": months_list,
        "categories": categories,
        "total_spending": round(total_yearly, 2),
        "average_monthly_spending": round(avg_monthly, 2),
        "highest_spending_month": highest["month"] if highest else None,
        "highest_spending_amount": round(highest["total_spending"], 2) if highest else 0.0,
        "months_with_data": len(non_zero),
    }
