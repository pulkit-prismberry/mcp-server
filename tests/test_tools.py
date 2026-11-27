"""Unit tests for the 6 canonical MCP tools (Contract v2.3 Final)."""
import unittest

from tools.tickets import (
    add_internal_note,
    create_ticket,
    get_ticket_details,
    issue_refund,
    search_tickets,
    update_ticket_status,
)
from data.mock_identities import ALICE_CONTEXT, BOB_CONTEXT


class TestGetTicketDetails(unittest.TestCase):
    def test_get_existing_ticket_101(self):
        result = get_ticket_details(101, user_context=BOB_CONTEXT)
        self.assertTrue(result["success"])
        self.assertIsNone(result["error"])
        self.assertIsNotNone(result["data"])
        self.assertEqual(result["data"]["ticket_id"], 101)

    def test_ticket_not_found(self):
        result = get_ticket_details(99999, user_context=BOB_CONTEXT)
        self.assertFalse(result["success"])
        self.assertIsNone(result["data"])
        self.assertEqual(result["error"]["code"], "NOT_FOUND")

    def test_validation_error_zero(self):
        result = get_ticket_details(0, user_context=BOB_CONTEXT)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "VALIDATION_ERROR")

    def test_validation_error_negative(self):
        result = get_ticket_details(-5, user_context=BOB_CONTEXT)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "VALIDATION_ERROR")


class TestSearchTickets(unittest.TestCase):
    def test_search_all_default(self):
        result = search_tickets(user_context=BOB_CONTEXT)
        self.assertTrue(result["success"])
        self.assertIsInstance(result["data"], list)

    def test_search_by_query_matching(self):
        result = search_tickets(query="subscription", user_context=BOB_CONTEXT)
        self.assertTrue(result["success"])
        self.assertGreaterEqual(len(result["data"]), 1)

    def test_search_by_query_non_matching(self):
        result = search_tickets(query="nonexistent_xyz_phrase", user_context=BOB_CONTEXT)
        self.assertTrue(result["success"])
        self.assertEqual(len(result["data"]), 0)

    def test_search_by_status(self):
        result = search_tickets(status="open", user_context=BOB_CONTEXT)
        self.assertTrue(result["success"])
        for ticket in result["data"]:
            self.assertEqual(ticket["status"].lower(), "open")


class TestCreateAndModifyTicket(unittest.TestCase):
    def test_create_ticket_success(self):
        result = create_ticket(
            title="Cannot connect to API",
            description="API endpoint returning 504 gateway timeout.",
            category="technical",
            priority="urgent",
            user_context=BOB_CONTEXT,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["category"], "technical")
        self.assertEqual(result["data"]["priority"], "urgent")

    def test_update_status_success(self):
        from data.mock_tickets import MOCK_TICKETS
        MOCK_TICKETS[101]["status"] = "open"
        result = update_ticket_status(101, "in_progress", user_context=BOB_CONTEXT)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["status"], "in_progress")

    def test_update_status_invalid_status(self):
        result = update_ticket_status(101, "flying_in_space", user_context=BOB_CONTEXT)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
