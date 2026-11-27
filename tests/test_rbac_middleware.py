"""Unit tests for Tool-Level RBAC Enforcement prior to DB execution."""
import asyncio
import unittest
from unittest.mock import patch

from data.mock_identities import BOB_CONTEXT, CHARLIE_CONTEXT
from server import mcp
from tools.tickets import (
    add_internal_note,
    create_ticket,
    get_ticket_details,
    issue_refund,
    search_tickets,
    update_ticket_status,
)


class TestToolLevelRBACEnforcement(unittest.TestCase):
    """Verify @require_permissions blocks unauthorized callers before any DB or service call."""

    NO_PERMS_USER = {
        "user_id": "99999999-9999-9999-9999-999999999999",
        "org_id": "11111111-1111-1111-1111-111111111111",
        "role": "Guest",
        "permissions": [],
        "is_active": True,
    }

    @patch("services.ticket_service.TicketRepository")
    @patch("services.ticket_service.TicketService.issue_refund")
    def test_issue_refund_blocked_for_non_org_admin_before_db(self, mock_svc, mock_repo):
        for caller in (BOB_CONTEXT, CHARLIE_CONTEXT):
            res = issue_refund(
                invoice_id="3b62e5dd-bf14-5ab9-bb03-6abd9fe3395f",
                amount="50.00",
                reason="Unauthorized refund attempt",
                idempotency_key="idemp-rbac-block-1",
                user_context=caller,
            )
            self.assertFalse(res["success"])
            self.assertEqual(res["error"]["code"], "FORBIDDEN")
            self.assertEqual(res["error"]["details"]["error_type"], "PermissionDenied")
            self.assertEqual(res["error"]["details"]["tool"], "issue_refund")
            self.assertEqual(res["error"]["details"]["required_permissions"], ["refund.issue"])
            self.assertEqual(res["error"]["details"]["role"], caller["role"])

        mock_svc.assert_not_called()
        mock_repo.get_refund_by_idempotency_key.assert_not_called()
        mock_repo.get_invoice.assert_not_called()

    @patch("services.ticket_service.TicketRepository")
    @patch("services.ticket_service.TicketService.add_internal_note")
    def test_add_internal_note_blocked_for_end_customer_before_db(self, mock_svc, mock_repo):
        res = add_internal_note(
            ticket_id="769a2504-7c6c-5950-88f9-6382cfeafd12",
            note="Customer attempting private whisper",
            user_context=CHARLIE_CONTEXT,
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "FORBIDDEN")
        self.assertEqual(res["error"]["details"]["error_type"], "PermissionDenied")
        self.assertEqual(res["error"]["details"]["tool"], "add_internal_note")
        self.assertEqual(res["error"]["details"]["required_permissions"], ["ticket.note:write"])
        self.assertEqual(res["error"]["details"]["role"], "End_Customer")

        mock_svc.assert_not_called()
        mock_repo.get_by_id.assert_not_called()
        mock_repo.add_internal_note.assert_not_called()

    @patch("services.ticket_service.TicketRepository")
    def test_all_ticket_tools_block_zero_permission_user_before_db(self, mock_repo):
        calls = [
            ("get_ticket_details", get_ticket_details("769a2504-7c6c-5950-88f9-6382cfeafd12", user_context=self.NO_PERMS_USER)),
            ("search_tickets", search_tickets(query="billing", user_context=self.NO_PERMS_USER)),
            ("create_ticket", create_ticket(title="Blocked", description="Should be blocked before DB", user_context=self.NO_PERMS_USER)),
            ("update_ticket_status", update_ticket_status("769a2504-7c6c-5950-88f9-6382cfeafd12", "closed", user_context=self.NO_PERMS_USER)),
            ("add_internal_note", add_internal_note("769a2504-7c6c-5950-88f9-6382cfeafd12", "note", user_context=self.NO_PERMS_USER)),
            ("issue_refund", issue_refund("inv-1", "10.00", "reason", "idemp-1", user_context=self.NO_PERMS_USER)),
        ]
        for tool_name, res in calls:
            self.assertFalse(res["success"], f"{tool_name} should fail")
            self.assertEqual(res["error"]["code"], "FORBIDDEN")
            self.assertEqual(res["error"]["details"]["error_type"], "PermissionDenied")
            self.assertEqual(res["error"]["details"]["tool"], tool_name)

        self.assertEqual(mock_repo.method_calls, [])

    def test_fastmcp_preserves_all_registered_tools_and_hides_ctx(self):
        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
        expected = {
            "get_ticket_details",
            "search_tickets",
            "create_ticket",
            "update_ticket_status",
            "add_internal_note",
            "issue_refund",
            "check_health",
            "check_liveness",
            "check_readiness",
        }
        self.assertTrue(expected.issubset(names))
        for t in tools:
            if t.name in expected - {"check_health", "check_liveness", "check_readiness"}:
                props = (t.inputSchema or {}).get("properties", {})
                self.assertNotIn("ctx", props, f"FastMCP Context 'ctx' leaked into {t.name} schema")


if __name__ == "__main__":
    unittest.main()
