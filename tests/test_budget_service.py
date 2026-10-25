"""Tests for budget-service: category budgets and overall monthly budgets."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "budget-service"
    / "app"
    / "main.py"
)

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["SMARTSPEND_TEST_DB"] = _tmp.name  # not used by budget svc but set for safety

spec = importlib.util.spec_from_file_location("budget_main", SERVICE_PATH)
module = importlib.util.module_from_spec(spec)

# Point to a temp DB before module executes
import sqlite3
_budget_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_budget_tmp.close()

spec.loader.exec_module(module)
module.DB_PATH = Path(_budget_tmp.name)


class TestCategoryBudgets(unittest.TestCase):
    def setUp(self):
        module.DB_PATH = Path(_budget_tmp.name)
        module.initialize_database()
        with module.get_connection() as conn:
            conn.execute("DELETE FROM budgets")
            conn.execute("DELETE FROM monthly_budgets")
        self.client = TestClient(module.app)

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "healthy")

    def test_create_category_budget(self):
        r = self.client.post(
            "/budgets",
            json={"category": "Food", "monthly_limit": 5000, "month": "2026-10"},
        )
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data["category"], "Food")
        self.assertEqual(data["monthly_limit"], 5000)
        self.assertEqual(data["month"], "2026-10")

    def test_duplicate_category_budget_returns_409(self):
        self.client.post(
            "/budgets",
            json={"category": "Food", "monthly_limit": 5000, "month": "2026-10"},
        )
        r = self.client.post(
            "/budgets",
            json={"category": "Food", "monthly_limit": 6000, "month": "2026-10"},
        )
        self.assertEqual(r.status_code, 409)

    def test_list_budgets_filtered_by_month(self):
        self.client.post(
            "/budgets",
            json={"category": "Food", "monthly_limit": 5000, "month": "2026-10"},
        )
        self.client.post(
            "/budgets",
            json={"category": "Transport", "monthly_limit": 2000, "month": "2026-09"},
        )
        r = self.client.get("/budgets?month=2026-10")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["category"], "Food")

    def test_update_category_budget(self):
        r = self.client.post(
            "/budgets",
            json={"category": "Food", "monthly_limit": 5000, "month": "2026-10"},
        )
        budget_id = r.json()["id"]
        r2 = self.client.put(
            f"/budgets/{budget_id}",
            json={"category": "Food", "monthly_limit": 7500, "month": "2026-10"},
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["monthly_limit"], 7500)

    def test_delete_category_budget(self):
        r = self.client.post(
            "/budgets",
            json={"category": "Bills", "monthly_limit": 3000, "month": "2026-10"},
        )
        budget_id = r.json()["id"]
        r2 = self.client.delete(f"/budgets/{budget_id}")
        self.assertEqual(r2.status_code, 200)
        r3 = self.client.delete(f"/budgets/{budget_id}")
        self.assertEqual(r3.status_code, 404)

    def test_invalid_month_format(self):
        r = self.client.post(
            "/budgets",
            json={"category": "Food", "monthly_limit": 5000, "month": "2026-13"},
        )
        self.assertEqual(r.status_code, 422)


class TestOverallMonthlyBudgets(unittest.TestCase):
    def setUp(self):
        module.DB_PATH = Path(_budget_tmp.name)
        module.initialize_database()
        with module.get_connection() as conn:
            conn.execute("DELETE FROM budgets")
            conn.execute("DELETE FROM monthly_budgets")
        self.client = TestClient(module.app)

    def test_create_monthly_budget(self):
        r = self.client.post(
            "/monthly-budgets",
            json={"month": "2026-10", "amount": 20000},
        )
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data["month"], "2026-10")
        self.assertEqual(data["amount"], 20000)

    def test_duplicate_monthly_budget_returns_409(self):
        self.client.post(
            "/monthly-budgets", json={"month": "2026-10", "amount": 20000}
        )
        r = self.client.post(
            "/monthly-budgets", json={"month": "2026-10", "amount": 25000}
        )
        self.assertEqual(r.status_code, 409)

    def test_get_monthly_budget(self):
        self.client.post(
            "/monthly-budgets", json={"month": "2026-10", "amount": 20000}
        )
        r = self.client.get("/monthly-budgets/2026-10")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["amount"], 20000)

    def test_missing_month_returns_404(self):
        r = self.client.get("/monthly-budgets/2020-01")
        self.assertEqual(r.status_code, 404)

    def test_update_monthly_budget(self):
        self.client.post(
            "/monthly-budgets", json={"month": "2026-10", "amount": 20000}
        )
        r = self.client.put("/monthly-budgets/2026-10", json={"amount": 25000})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["amount"], 25000)

    def test_update_nonexistent_returns_404(self):
        r = self.client.put("/monthly-budgets/1999-01", json={"amount": 10000})
        self.assertEqual(r.status_code, 404)

    def test_delete_monthly_budget(self):
        self.client.post(
            "/monthly-budgets", json={"month": "2026-11", "amount": 18000}
        )
        r = self.client.delete("/monthly-budgets/2026-11")
        self.assertEqual(r.status_code, 200)
        r2 = self.client.get("/monthly-budgets/2026-11")
        self.assertEqual(r2.status_code, 404)

    def test_list_monthly_budgets(self):
        self.client.post(
            "/monthly-budgets", json={"month": "2026-09", "amount": 18000}
        )
        self.client.post(
            "/monthly-budgets", json={"month": "2026-10", "amount": 20000}
        )
        r = self.client.get("/monthly-budgets")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data), 2)
        # Should be ordered newest first
        self.assertEqual(data[0]["month"], "2026-10")


if __name__ == "__main__":
    unittest.main()
