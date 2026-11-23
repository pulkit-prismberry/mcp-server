"""Comprehensive unit test suite for Contract v2.3 Final."""
import unittest

from tools.tickets import (
    add_internal_note,
    check_health,
    create_ticket,
    get_ticket_details,
    issue_refund,
    search_tickets,
    update_ticket_status,
)
from utils.auth import (
    ALICE_CONTEXT,
    BOB_CONTEXT,
    CHARLIE_CONTEXT,
    DAVE_CONTEXT,
    generate_approval_token,
    generate_jwt,
    verify_jwt,
)


class TestContractV23IdentitiesAndJWT(unittest.TestCase):
    def test_deterministic_identities(self):
        # Charlie customer_id is distinct from user_id
        self.assertEqual(CHARLIE_CONTEXT["user_id"], "ccccccc1-1111-1111-1111-111111111111")
        self.assertEqual(CHARLIE_CONTEXT["customer_id"], "ccccccc2-2222-2222-2222-222222222222")
        self.assertIsNone(ALICE_CONTEXT["customer_id"])
        self.assertIsNone(BOB_CONTEXT["customer_id"])
        self.assertIsNone(DAVE_CONTEXT["customer_id"])

    def test_jwt_claims_and_pinned_hs256(self):
        token = generate_jwt(CHARLIE_CONTEXT)
        verified = verify_jwt(token)
        self.assertEqual(verified["user_id"], CHARLIE_CONTEXT["user_id"])
        self.assertEqual(verified["customer_id"], CHARLIE_CONTEXT["customer_id"])
        self.assertEqual(verified["org_id"], CHARLIE_CONTEXT["org_id"])
        self.assertEqual(verified["role"], "End_Customer")


class TestContractV23HealthProbe(unittest.TestCase):
    def test_health_probe(self):
        health = check_health()
        self.assertEqual(health["status"], "available")
        self.assertIn("database", health)
        self.assertEqual(health["version"], "1.0.0")


class TestContractV23Tool1GetTicketDetails(unittest.TestCase):
    def test_charlie_views_own_ticket(self):
        res = get_ticket_details(101, user_context=CHARLIE_CONTEXT)
        self.assertTrue(res.get("success"))
        self.assertEqual(res["data"]["customer_id"], CHARLIE_CONTEXT["customer_id"])

    def test_charlie_cannot_view_other_ticket(self):
        res = get_ticket_details(102, user_context=CHARLIE_CONTEXT)
        self.assertFalse(res.get("success"))
        self.assertEqual(res["error"]["code"], "NOT_FOUND")

    def test_dave_cannot_view_org_a_ticket(self):
        res = get_ticket_details(101, user_context=DAVE_CONTEXT)
        self.assertFalse(res.get("success"))
        self.assertEqual(res["error"]["code"], "NOT_FOUND")

    def test_bob_views_any_org_a_ticket(self):
        res1 = get_ticket_details(101, user_context=BOB_CONTEXT)
        res2 = get_ticket_details(102, user_context=BOB_CONTEXT)
        self.assertTrue(res1.get("success"))
        self.assertTrue(res2.get("success"))


class TestContractV23Tool2SearchTickets(unittest.TestCase):
    def test_substring_search_matching(self):
        res = search_tickets(query="renewal", user_context=BOB_CONTEXT)
        self.assertTrue(res.get("success"))
        self.assertGreaterEqual(len(res["data"]), 1)

    def test_charlie_searches_strictly_own_tickets(self):
        res = search_tickets(query="authentication", user_context=CHARLIE_CONTEXT)
        self.assertTrue(res.get("success"))
        self.assertEqual(len(res["data"]), 0)  # Ticket 102 has authentication but belongs to another customer


class TestContractV23Tool3CreateTicket(unittest.TestCase):
    def test_customer_creation_auto_binds_customer_id(self):
        res = create_ticket(
            title="Customer Mobile Bug",
            description="App crashes on checkout screen.",
            category="technical",
            customer_id="malicious_spoofed_id",  # Passed id must be ignored
            user_context=CHARLIE_CONTEXT,
        )
        self.assertTrue(res.get("success"))
        self.assertEqual(res["data"]["customer_id"], CHARLIE_CONTEXT["customer_id"])
        self.assertEqual(res["data"]["status"], "open")

    def test_staff_creation_with_valid_customer(self):
        res = create_ticket(
            title="Manual Staff Ticket",
            description="Created by Bob on behalf of Charlie.",
            category="billing",
            customer_id=CHARLIE_CONTEXT["customer_id"],
            user_context=BOB_CONTEXT,
        )
        self.assertTrue(res.get("success"))
        self.assertEqual(res["data"]["customer_id"], CHARLIE_CONTEXT["customer_id"])

    def test_staff_creation_with_cross_tenant_customer_fails(self):
        # cust_b belongs to Org B, Bob is in Org A
        res = create_ticket(
            title="Invalid Cross-Tenant Ticket",
            description="Attempt to assign Org B customer.",
            category="billing",
            customer_id="cust_b_3333-3333-3333-333333333333",
            user_context=BOB_CONTEXT,
        )
        self.assertFalse(res.get("success"))
        self.assertEqual(res["error"]["code"], "NOT_FOUND")


class TestContractV23Tool4UpdateTicketStatus(unittest.TestCase):
    def test_staff_follows_valid_lifecycle(self):
        # 101 is open -> in_progress
        res1 = update_ticket_status(101, "in_progress", user_context=BOB_CONTEXT)
        self.assertTrue(res1.get("success"))
        self.assertEqual(res1["data"]["status"], "in_progress")

        # in_progress -> resolved
        res2 = update_ticket_status(101, "resolved", user_context=BOB_CONTEXT)
        self.assertTrue(res2.get("success"))
        self.assertEqual(res2["data"]["status"], "resolved")

    def test_invalid_lifecycle_transition_returns_conflict(self):
        # 102 is in_progress -> cannot jump to open
        res = update_ticket_status(102, "open", user_context=BOB_CONTEXT)
        self.assertFalse(res.get("success"))
        self.assertEqual(res["error"]["code"], "CONFLICT")

    def test_customer_can_only_close_resolved_ticket(self):
        # Ensure 101 is resolved
        from data.mock_tickets import MOCK_TICKETS
        MOCK_TICKETS[101]["status"] = "resolved"
        res = update_ticket_status(101, "closed", user_context=CHARLIE_CONTEXT)
        self.assertTrue(res.get("success"))
        self.assertEqual(res["data"]["status"], "closed")

    def test_customer_cannot_move_closed_ticket(self):
        # Ensure 101 is closed
        from data.mock_tickets import MOCK_TICKETS
        MOCK_TICKETS[101]["status"] = "closed"
        res = update_ticket_status(101, "in_progress", user_context=CHARLIE_CONTEXT)
        self.assertFalse(res.get("success"))
        self.assertEqual(res["error"]["code"], "FORBIDDEN")


class TestContractV23Tool5AddInternalNote(unittest.TestCase):
    def test_customer_forbidden(self):
        res = add_internal_note(101, "Customer note attempt", user_context=CHARLIE_CONTEXT)
        self.assertFalse(res.get("success"))
        self.assertEqual(res["error"]["code"], "FORBIDDEN")

    def test_staff_note_output_shape(self):
        res = add_internal_note(101, "Staff investigation note.", user_context=BOB_CONTEXT)
        self.assertTrue(res.get("success"))
        data = res["data"]
        self.assertIn("id", data)
        self.assertIn("ticket_id", data)
        self.assertIn("org_id", data)
        self.assertIn("author_id", data)
        self.assertEqual(data["note"], "Staff investigation note.")
        self.assertIn("created_at", data)


class TestContractV23Tool6IssueRefund(unittest.TestCase):
    def test_support_agent_forbidden(self):
        res = issue_refund(
            invoice_id="inv_org_a_001",
            amount="50.00",
            reason="Customer request",
            idempotency_key="idemp_bob_refund",
            user_context=BOB_CONTEXT,
        )
        self.assertFalse(res.get("success"))
        self.assertEqual(res["error"]["code"], "FORBIDDEN")

    def test_high_value_refund_without_token_forbidden(self):
        res = issue_refund(
            invoice_id="inv_org_a_001",
            amount="250.00",
            reason="Overcharge on subscription",
            idempotency_key="idemp_alice_no_tok",
            approval_token=None,
            user_context=ALICE_CONTEXT,
        )
        self.assertFalse(res.get("success"))
        self.assertEqual(res["error"]["code"], "FORBIDDEN")

    def test_high_value_refund_with_valid_token_and_single_use(self):
        invoice_id = "inv_org_a_001"
        amount = 150.00
        org_id = ALICE_CONTEXT["org_id"]
        token = generate_approval_token(invoice_id, amount, org_id, approver_id=ALICE_CONTEXT["user_id"])

        # First execution -> Success
        res1 = issue_refund(
            invoice_id=invoice_id,
            amount=amount,
            reason="Customer overcharge",
            idempotency_key="idemp_single_use_first",
            approval_token=token,
            user_context=ALICE_CONTEXT,
        )
        self.assertTrue(res1.get("success"))
        self.assertEqual(res1["data"]["status"], "partially_refunded")
        self.assertEqual(res1["data"]["refunded_amount"], 150.00)

        # Second execution with same token -> Single use consumed -> 403 FORBIDDEN
        res2 = issue_refund(
            invoice_id=invoice_id,
            amount=amount,
            reason="Attempting reuse of consumed token",
            idempotency_key="idemp_single_use_second",
            approval_token=token,
            user_context=ALICE_CONTEXT,
        )
        self.assertFalse(res2.get("success"))
        self.assertEqual(res2["error"]["code"], "FORBIDDEN")
        self.assertIn("consumed", res2["error"]["message"])

    def test_refund_exceeding_balance_conflict(self):
        # Balance is 500 - 150 = 350
        res = issue_refund(
            invoice_id="inv_org_a_001",
            amount="999.00",
            reason="Too large",
            idempotency_key="idemp_too_large",
            approval_token="any_token",
            user_context=ALICE_CONTEXT,
        )
        self.assertFalse(res.get("success"))
        self.assertEqual(res["error"]["code"], "CONFLICT")


if __name__ == "__main__":
    unittest.main()
