"""Unit tests for TicketService."""
import unittest
from services.ticket_service import TicketService
from utils.auth import BOB_CONTEXT


class TestTicketService(unittest.TestCase):
    def test_get_existing(self):
        res = TicketService.get_ticket(101, user_context=BOB_CONTEXT)
        self.assertTrue(res.get("success"))
        self.assertEqual(res["data"]["ticket_id"], 101)

    def test_get_nonexistent(self):
        res = TicketService.get_ticket(9999, user_context=BOB_CONTEXT)
        self.assertFalse(res.get("success"))
        self.assertEqual(res["error"]["code"], "NOT_FOUND")

    def test_list_tickets(self):
        tickets = TicketService.list_tickets()
        self.assertIsInstance(tickets, list)
        self.assertGreaterEqual(len(tickets), 2)


if __name__ == "__main__":
    unittest.main()
