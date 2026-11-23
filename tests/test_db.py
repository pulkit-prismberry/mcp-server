"""Unit tests for PostgreSQL ticket repository and database service integration."""
from datetime import date, datetime
from decimal import Decimal
import unittest
from unittest.mock import MagicMock, patch

from db.ticket_repository import TicketRepository, _serialize_row
from services.ticket_service import TicketService
from utils.auth import BOB_CONTEXT


class TestDatabaseRepository(unittest.TestCase):
    def test_serialize_row(self):
        raw = {
            "ticket_id": 101,
            "purchase_date": date(2026, 1, 15),
            "created_at": datetime(2026, 1, 15, 12, 0, 0),
            "satisfaction_rating": Decimal("4.5"),
            "status": "open",
        }
        serialized = _serialize_row(raw)
        self.assertEqual(serialized["ticket_id"], 101)
        self.assertEqual(serialized["purchase_date"], "2026-01-15")
        self.assertEqual(serialized["created_at"], "2026-01-15T12:00:00")
        self.assertEqual(serialized["satisfaction_rating"], 4.5)
        self.assertEqual(serialized["status"], "open")

    @patch("db.ticket_repository.get_db_connection")
    def test_get_by_id_found_in_normalized(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        sample_db_row = {
            "ticket_id": 200,
            "subject": "DB Ticket Subject",
            "description": "DB Description",
            "status": "resolved",
            "priority": "low",
            "customer_id": 1,
            "customer_name": "Alice Doe",
            "customer_email": "alice@example.com",
            "customer_age": 28,
            "customer_gender": "Female",
            "product_purchased": "Product X",
            "purchase_date": date(2026, 2, 1),
            "ticket_type": "Technical issue",
            "ticket_channel": "Email",
            "resolution": "Resolved quickly",
            "first_response_at": datetime(2026, 2, 1, 10, 0),
            "resolved_at": datetime(2026, 2, 1, 11, 0),
            "satisfaction_rating": Decimal("5.0"),
            "created_at": datetime(2026, 2, 1, 9, 0),
            "updated_at": datetime(2026, 2, 1, 11, 0),
        }
        mock_cursor.fetchone.return_value = sample_db_row

        result = TicketRepository.get_by_id(200)
        self.assertIsNotNone(result)
        self.assertEqual(result["ticket_id"], 200)
        self.assertEqual(result["subject"], "DB Ticket Subject")
        self.assertEqual(result["customer_name"], "Alice Doe")
        self.assertEqual(result["satisfaction_rating"], 5.0)

    @patch("db.ticket_repository.get_db_connection")
    def test_update_ticket_status_in_db(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchone.return_value = (3,)
        mock_cursor.rowcount = 1

        success = TicketRepository.update_ticket_status(101, "resolved", reason="Issue solved")
        self.assertTrue(success)
        mock_conn.commit.assert_called()


if __name__ == "__main__":
    unittest.main()
