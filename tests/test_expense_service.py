
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "expense-service"
    / "app"
    / "main.py"
)

temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
temp_file.close()

os.environ["SMARTSPEND_TEST_DB"] = temp_file.name

spec = importlib.util.spec_from_file_location("expense_main", SERVICE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

module.DB_PATH = Path(temp_file.name)


class TestExpenseService(unittest.TestCase):
    def setUp(self):
        module.initialize_database()

        with module.get_connection() as connection:
            connection.execute("DELETE FROM expenses")

        self.client_context = TestClient(module.app)
        self.client_context.__enter__()
        self.client = self.client_context

    def tearDown(self):
        self.client_context.__exit__(None, None, None)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_create_and_list_expense(self):
        response = self.client.post(
            "/expenses",
            json={
                "description": "Groceries",
                "amount": 500,
                "category": "Food",
                "date": "2026-10-19",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["description"], "Groceries")

        listing = self.client.get("/expenses")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()), 1)

    def test_reject_invalid_amount(self):
        response = self.client.post(
            "/expenses",
            json={
                "description": "Invalid",
                "amount": -5,
                "category": "Food",
                "date": "2026-10-19",
            },
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
