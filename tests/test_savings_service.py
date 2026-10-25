"""Tests for savings-service: balance, ledger, idempotency, goals, contributions."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVICE_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "savings-service"
    / "app"
    / "main.py"
)

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["SMARTSPEND_SAVINGS_DB"] = _tmp.name

spec = importlib.util.spec_from_file_location("savings_main", SERVICE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.DB_PATH = Path(_tmp.name)


class TestSavingsService(unittest.TestCase):
    def setUp(self):
        module.DB_PATH = Path(_tmp.name)
        module.initialize_database()
        with module.get_connection() as conn:
            conn.execute("DELETE FROM savings_ledger")
            conn.execute("DELETE FROM savings_allocations")
            conn.execute("DELETE FROM savings_goals")
        self.client = TestClient(module.app)

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)

    def test_initial_balance_zero(self):
        r = self.client.get("/savings/balance")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["balance"], 0.0)

    def test_deposit_increases_balance(self):
        r = self.client.post("/savings/deposit", json={"amount": 5000})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["balance_after"], 5000.0)

    def test_withdrawal_decreases_balance(self):
        self.client.post("/savings/deposit", json={"amount": 5000})
        r = self.client.post("/savings/withdraw", json={"amount": 2000})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["balance_after"], 3000.0)

    def test_withdrawal_exceeding_balance_rejected(self):
        self.client.post("/savings/deposit", json={"amount": 1000})
        r = self.client.post("/savings/withdraw", json={"amount": 5000})
        self.assertEqual(r.status_code, 422)

    def test_negative_deposit_rejected(self):
        r = self.client.post("/savings/deposit", json={"amount": -100})
        self.assertEqual(r.status_code, 422)

    def test_idempotent_deposit(self):
        key = "test-idem-key-deposit-001"
        r1 = self.client.post(
            "/savings/deposit", json={"amount": 1000, "idempotency_key": key}
        )
        r2 = self.client.post(
            "/savings/deposit", json={"amount": 1000, "idempotency_key": key}
        )
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertTrue(r2.json().get("idempotent"))
        # Balance should only increase once
        balance = self.client.get("/savings/balance").json()["balance"]
        self.assertEqual(balance, 1000.0)

    def test_idempotent_withdrawal(self):
        self.client.post("/savings/deposit", json={"amount": 3000})
        key = "test-idem-key-withdraw-001"
        self.client.post(
            "/savings/withdraw", json={"amount": 500, "idempotency_key": key}
        )
        self.client.post(
            "/savings/withdraw", json={"amount": 500, "idempotency_key": key}
        )
        balance = self.client.get("/savings/balance").json()["balance"]
        self.assertEqual(balance, 2500.0)

    def test_list_transactions(self):
        self.client.post("/savings/deposit", json={"amount": 2000})
        self.client.post("/savings/withdraw", json={"amount": 500})
        r = self.client.get("/savings/transactions")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["balance"], 1500.0)

    def test_allocate_unspent_monthly_budget(self):
        with patch.object(module, "_budget_and_spending", return_value=(20000, 6000)):
            response = self.client.post(
                "/savings/allocate",
                json={
                    "month": "2026-10",
                    "amount": 4000,
                    "idempotency_key": "allocation-2026-10-1",
                },
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["available_after"], 10000.0)

            repeated = self.client.post(
                "/savings/allocate",
                json={
                    "month": "2026-10",
                    "amount": 4000,
                    "idempotency_key": "allocation-2026-10-1",
                },
            )
            self.assertTrue(repeated.json()["idempotent"])
            self.assertEqual(
                self.client.get("/savings/balance").json()["balance"], 4000.0
            )

            excessive = self.client.post(
                "/savings/allocate",
                json={"month": "2026-10", "amount": 10001},
            )
            self.assertEqual(excessive.status_code, 422)

    def test_allocation_idempotency_key_cannot_change_request(self):
        with patch.object(module, "_budget_and_spending", return_value=(20000, 0)):
            self.client.post(
                "/savings/allocate",
                json={
                    "month": "2026-10",
                    "amount": 4000,
                    "idempotency_key": "allocation-fixed-key",
                },
            )
            response = self.client.post(
                "/savings/allocate",
                json={
                    "month": "2026-10",
                    "amount": 5000,
                    "idempotency_key": "allocation-fixed-key",
                },
            )
        self.assertEqual(response.status_code, 409)

    def test_allocation_rejects_invalid_month(self):
        response = self.client.post(
            "/savings/allocate",
            json={"month": "2026-13", "amount": 100},
        )
        self.assertEqual(response.status_code, 422)


class TestSavingsGoals(unittest.TestCase):
    def setUp(self):
        module.DB_PATH = Path(_tmp.name)
        module.initialize_database()
        with module.get_connection() as conn:
            conn.execute("DELETE FROM savings_ledger")
            conn.execute("DELETE FROM savings_allocations")
            conn.execute("DELETE FROM savings_goals")
        self.client = TestClient(module.app)

    def test_create_goal(self):
        r = self.client.post(
            "/savings/goals",
            json={"name": "Laptop", "target_amount": 80000},
        )
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data["name"], "Laptop")
        self.assertEqual(data["target_amount"], 80000)
        self.assertEqual(data["current_amount"], 0.0)
        self.assertEqual(data["progress_pct"], 0.0)

    def test_list_goals(self):
        self.client.post(
            "/savings/goals", json={"name": "Laptop", "target_amount": 80000}
        )
        self.client.post(
            "/savings/goals", json={"name": "Phone", "target_amount": 50000}
        )
        r = self.client.get("/savings/goals")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 2)

    def test_contribute_to_goal(self):
        # Deposit first
        self.client.post("/savings/deposit", json={"amount": 10000})
        # Create goal
        goal_r = self.client.post(
            "/savings/goals", json={"name": "Laptop", "target_amount": 80000}
        )
        goal_id = goal_r.json()["id"]
        # Contribute
        r = self.client.post(
            f"/savings/goals/{goal_id}/contribute",
            json={"amount": 5000},
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["balance_after"], 5000.0)
        self.assertEqual(r.json()["goal"]["current_amount"], 5000.0)

    def test_contribution_exceeding_balance_rejected(self):
        self.client.post("/savings/deposit", json={"amount": 1000})
        goal_r = self.client.post(
            "/savings/goals", json={"name": "Car", "target_amount": 500000}
        )
        goal_id = goal_r.json()["id"]
        r = self.client.post(
            f"/savings/goals/{goal_id}/contribute", json={"amount": 50000}
        )
        self.assertEqual(r.status_code, 422)

    def test_withdraw_from_goal_returns_money_to_wallet(self):
        self.client.post("/savings/deposit", json={"amount": 5000})
        goal_id = self.client.post(
            "/savings/goals",
            json={"name": "Laptop", "target_amount": 80000},
        ).json()["id"]
        self.client.post(
            f"/savings/goals/{goal_id}/contribute",
            json={"amount": 3000},
        )
        response = self.client.post(
            f"/savings/goals/{goal_id}/withdraw",
            json={"amount": 1000},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["goal"]["current_amount"], 2000.0)
        self.assertEqual(self.client.get("/savings/balance").json()["balance"], 3000.0)

    def test_goal_date_must_be_a_real_calendar_date(self):
        response = self.client.post(
            "/savings/goals",
            json={
                "name": "Trip",
                "target_amount": 10000,
                "target_date": "2026-02-30",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_idempotent_contribution(self):
        self.client.post("/savings/deposit", json={"amount": 10000})
        goal_r = self.client.post(
            "/savings/goals", json={"name": "Vacation", "target_amount": 30000}
        )
        goal_id = goal_r.json()["id"]
        key = "contrib-idem-001"
        self.client.post(
            f"/savings/goals/{goal_id}/contribute",
            json={"amount": 1000, "idempotency_key": key},
        )
        self.client.post(
            f"/savings/goals/{goal_id}/contribute",
            json={"amount": 1000, "idempotency_key": key},
        )
        balance = self.client.get("/savings/balance").json()["balance"]
        self.assertEqual(balance, 9000.0)  # 10000 - 1000 (only once)

    def test_goal_progress_pct(self):
        self.client.post("/savings/deposit", json={"amount": 20000})
        goal_r = self.client.post(
            "/savings/goals", json={"name": "Laptop", "target_amount": 80000}
        )
        goal_id = goal_r.json()["id"]
        self.client.post(
            f"/savings/goals/{goal_id}/contribute", json={"amount": 20000}
        )
        r = self.client.get(f"/savings/goals/{goal_id}")
        self.assertEqual(r.json()["progress_pct"], 25.0)

    def test_delete_goal(self):
        goal_r = self.client.post(
            "/savings/goals", json={"name": "Temp", "target_amount": 1000}
        )
        goal_id = goal_r.json()["id"]
        r = self.client.delete(f"/savings/goals/{goal_id}")
        self.assertEqual(r.status_code, 200)
        r2 = self.client.get(f"/savings/goals/{goal_id}")
        self.assertEqual(r2.status_code, 404)


if __name__ == "__main__":
    unittest.main()
