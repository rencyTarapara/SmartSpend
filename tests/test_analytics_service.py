import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

SERVICE_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "analytics-service"
    / "app"
    / "main.py"
)
spec = importlib.util.spec_from_file_location("analytics_main", SERVICE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TestAnalyticsService(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(module.app)

    def test_daily_response_includes_transaction_details(self):
        expenses = [
            {
                "id": 17,
                "description": "Lunch",
                "amount": 250,
                "category": "Food",
                "date": "2026-10-03",
            }
        ]
        with patch.object(module, "fetch_expenses", return_value=expenses):
            response = self.client.get("/analytics/daily?month=2026-10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["daily"][0]["transactions"], expenses)

    def test_yearly_response_has_twelve_months_and_includes_empty_months(self):
        expenses = [
            {
                "id": 1,
                "description": "Rent",
                "amount": 12000,
                "category": "Bills",
                "date": "2026-01-05",
            },
            {
                "id": 2,
                "description": "Groceries",
                "amount": 3000,
                "category": "Food",
                "date": "2026-01-10",
            },
        ]
        with patch.object(module, "fetch_expenses", return_value=expenses):
            response = self.client.get("/analytics/yearly?year=2026")

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(body["months"]), 12)
        self.assertEqual(body["months"][1]["total_spending"], 0)
        self.assertEqual(body["total_spending"], 15000)
        self.assertEqual(body["average_monthly_spending"], 1250)
        self.assertEqual(body["highest_spending_month"], "2026-01")
        self.assertEqual(body["categories"][0]["category"], "Bills")

    def test_yearly_response_without_expenses_has_zero_annual_average(self):
        with patch.object(module, "fetch_expenses", return_value=[]):
            response = self.client.get("/analytics/yearly?year=2026")

        body = response.json()
        self.assertEqual(body["total_spending"], 0)
        self.assertEqual(body["average_monthly_spending"], 0)
        self.assertIsNone(body["highest_spending_month"])
        self.assertEqual(body["categories"], [])


if __name__ == "__main__":
    unittest.main()
