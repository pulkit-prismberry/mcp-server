"""Comprehensive unit test suite for Team Contract v3.0 Locked."""
import unittest

from tools.tickets import (
    add_internal_note,
    check_health,
    check_liveness,
    check_readiness,
    create_ticket,
    get_ticket_details,
    issue_refund,
    search_tickets,
    update_ticket_status,
)
from data.mock_identities import (
    ALICE_CONTEXT,
    BOB_CONTEXT,
    CHARLIE_CONTEXT,
    DAVE_CONTEXT,
)
from utils.auth import (
    decode_raw_jwt_claims,
    generate_approval_hmac,
    generate_approval_token,
    generate_jwt,
    get_live_user_context,
    has_permission,
    resolve_auth_me,
    update_live_user_role,
    verify_jwt,
)


class TestContractV30IdentitiesAndAuth(unittest.TestCase):
    """Tests Section 1 & Section 2: Deterministic Identities, Lean Tokens, /auth/me."""

    def test_deterministic_identities_and_metadata(self):
        # Alice (Org_Admin, Org A)
        self.assertEqual(ALICE_CONTEXT["user_id"], "aaaaaaa1-1111-1111-1111-111111111111")
        self.assertEqual(ALICE_CONTEXT["org_id"], "11111111-1111-1111-1111-111111111111")
        self.assertIsNone(ALICE_CONTEXT["customer_id"])
        self.assertEqual(ALICE_CONTEXT["role"], "Org_Admin")
        self.assertEqual(ALICE_CONTEXT["permissions"], ["*"])
        self.assertIn("admin_only", ALICE_CONTEXT["authorized_kb_tiers"])

        # Bob (Support_Agent, Org A)
        self.assertEqual(BOB_CONTEXT["user_id"], "bbbbbbb1-1111-1111-1111-111111111111")
        self.assertIsNone(BOB_CONTEXT["customer_id"])
        self.assertIn("ticket.read:org", BOB_CONTEXT["permissions"])
        self.assertIn("ticket.note:write", BOB_CONTEXT["permissions"])

        # Charlie (End_Customer, Org A) - distinct customer_id
        self.assertEqual(CHARLIE_CONTEXT["user_id"], "ccccccc1-1111-1111-1111-111111111111")
        self.assertEqual(CHARLIE_CONTEXT["customer_id"], "ccccccc2-2222-2222-2222-222222222222")
        self.assertIn("ticket.read:own", CHARLIE_CONTEXT["permissions"])
        self.assertEqual(CHARLIE_CONTEXT["authorized_kb_tiers"], ["public"])

        # Dave (Org_Admin, Org B)
        self.assertEqual(DAVE_CONTEXT["user_id"], "ddddddd2-2222-2222-2222-222222222222")
        self.assertEqual(DAVE_CONTEXT["org_id"], "22222222-2222-2222-2222-222222222222")

    def test_lean_jwt_claims_structure(self):
        """Verify token is lean: role, org_id, and permissions are NOT baked into JWT (Section 2.B)."""
        token = generate_jwt(ALICE_CONTEXT, lean=True)
        raw_claims = decode_raw_jwt_claims(token)
        self.assertEqual(raw_claims["sub"], ALICE_CONTEXT["user_id"])
        self.assertEqual(raw_claims["user_id"], ALICE_CONTEXT["user_id"])
        self.assertEqual(raw_claims["iss"], "support-ai-backend")
        self.assertEqual(raw_claims["aud"], "support-ai-services")
        self.assertIn("exp", raw_claims)
        self.assertIn("iat", raw_claims)

        # Must NOT be statically baked into lean token
        self.assertNotIn("role", raw_claims)
        self.assertNotIn("org_id", raw_claims)
        self.assertNotIn("permissions", raw_claims)

    def test_dynamic_live_resolution_and_instant_revocation(self):
        """Verify dynamic resolution and zero-lag permission revocation (Section 2.B & 2.C)."""
        alice_uuid = ALICE_CONTEXT["user_id"]
        token = generate_jwt(ALICE_CONTEXT, lean=True)

        verified = verify_jwt(token)
        self.assertEqual(verified["role"], "Org_Admin")
        self.assertIn("*", verified["permissions"])

        # Instant permission revocation
        try:
            update_live_user_role(alice_uuid, new_role="Auditor", new_permissions=["ticket.read:org"])
            updated_verified = verify_jwt(token)
            self.assertEqual(updated_verified["role"], "Auditor")
            self.assertEqual(updated_verified["permissions"], ["ticket.read:org"])
        finally:
            update_live_user_role(alice_uuid, new_role="Org_Admin", new_permissions=["*"])

    def test_auth_me_endpoint_resolution(self):
        """Verify GET /auth/me resolution schema and disabled user handling (Section 2.C)."""
        status_code, me_data = resolve_auth_me("alice")
        self.assertEqual(status_code, 200)
        self.assertEqual(me_data["id"], ALICE_CONTEXT["user_id"])
        self.assertEqual(me_data["email"], "alice@orga.com")
        self.assertEqual(me_data["full_name"], "Alice Admin")
        self.assertEqual(me_data["org_id"], ALICE_CONTEXT["org_id"])
        self.assertIsNone(me_data["customer_id"])
        self.assertEqual(me_data["role"], "Org_Admin")
        self.assertEqual(me_data["permissions"], ["*"])
        self.assertEqual(me_data["authorized_kb_tiers"], ["public", "internal_staff", "admin_only"])

        # Test disabled user returns 401 UNAUTHORIZED
        disabled_context = dict(ALICE_CONTEXT)
        disabled_context["is_active"] = False
        status_code, err_data = resolve_auth_me(disabled_context)
        self.assertEqual(status_code, 401)
        self.assertEqual(err_data["error"]["code"], "UNAUTHORIZED")
        self.assertEqual(err_data["error"]["message"], "Account is disabled")


class TestContractV30HealthProbes(unittest.TestCase):
    """Tests Section 3.C: Liveness vs Readiness Probes."""

    def test_liveness_probe(self):
        live = check_liveness()
        self.assertEqual(live, {"status": "alive"})

    def test_readiness_probe(self):
        ready = check_readiness()
        self.assertEqual(ready["status"], "ready")

    def test_legacy_health_probe(self):
        health = check_health()
        self.assertEqual(health["status"], "available")
        self.assertEqual(health["version"], "1.0.0")


class TestContractV30RBACAndCanonicalPermissions(unittest.TestCase):
    """Tests Section 4: Canonical Permission Catalog enforcement."""

    def test_has_permission_checks_permissions_not_roles(self):
        # Custom user with only refund.issue permission
        auditor_user = {
            "user_id": "cust-auditor-1111",
            "role": "Custom_Auditor",
            "permissions": ["refund.issue"],
        }
        self.assertTrue(has_permission(auditor_user, "refund.issue"))
        self.assertFalse(has_permission(auditor_user, "ticket.note:write"))

        # Wildcard user has all permissions
        admin_user = {"role": "Custom_Role", "permissions": ["*"]}
        self.assertTrue(has_permission(admin_user, "ticket.read:org"))
        self.assertTrue(has_permission(admin_user, "refund.issue"))


class TestContractV30The6CanonicalTools(unittest.TestCase):
    """Tests Section 6: The 6 Canonical MCP Tools and Negative Test Matrix."""

    def test_tool1_get_ticket_details(self):
        # Charlie views own ticket
        res1 = get_ticket_details(101, user_context=CHARLIE_CONTEXT)
        self.assertTrue(res1.get("success"))
        self.assertEqual(res1["data"]["customer_id"], CHARLIE_CONTEXT["customer_id"])

        # Charlie viewing other's ticket -> 404 NOT_FOUND
        res2 = get_ticket_details(102, user_context=CHARLIE_CONTEXT)
        self.assertFalse(res2.get("success"))
        self.assertEqual(res2["error"]["code"], "NOT_FOUND")

        # Cross-Tenant Ticket Access: Dave (Org B) -> Org A ticket -> 404 NOT_FOUND
        res3 = get_ticket_details(101, user_context=DAVE_CONTEXT)
        self.assertFalse(res3.get("success"))
        self.assertEqual(res3["error"]["code"], "NOT_FOUND")

        # Bob (Staff with ticket.read:org) views any Org A ticket
        res4 = get_ticket_details(102, user_context=BOB_CONTEXT)
        self.assertTrue(res4.get("success"))

    def test_tool2_search_tickets(self):
        res1 = search_tickets(query="renewal", user_context=BOB_CONTEXT)
        self.assertTrue(res1.get("success"))
        self.assertGreaterEqual(len(res1["data"]), 1)

        # Charlie searches strictly own tickets
        res2 = search_tickets(query="authentication", user_context=CHARLIE_CONTEXT)
        self.assertTrue(res2.get("success"))
        self.assertEqual(len(res2["data"]), 0)

    def test_tool3_create_ticket(self):
        # Customer caller: customer_id bound automatically from JWT
        res1 = create_ticket(
            title="Customer Mobile Bug",
            description="App crashes on checkout screen.",
            category="technical",
            customer_id="spoofed_id",
            user_context=CHARLIE_CONTEXT,
        )
        self.assertTrue(res1.get("success"))
        self.assertEqual(res1["data"]["customer_id"], CHARLIE_CONTEXT["customer_id"])
        self.assertEqual(res1["data"]["status"], "open")

        # Staff caller with cross-tenant customer -> 404 NOT_FOUND
        res2 = create_ticket(
            title="Cross-tenant assignment",
            description="Assigning to Org B customer.",
            category="billing",
            customer_id="cust_b_3333-3333-3333-333333333333",
            user_context=BOB_CONTEXT,
        )
        self.assertFalse(res2.get("success"))
        self.assertEqual(res2["error"]["code"], "NOT_FOUND")

    def test_tool4_update_ticket_status(self):
        from data.mock_tickets import MOCK_TICKETS

        # Customer closing own resolved ticket -> Allowed
        MOCK_TICKETS[101]["status"] = "resolved"
        res1 = update_ticket_status(101, "closed", user_context=CHARLIE_CONTEXT)
        self.assertTrue(res1.get("success"))
        self.assertEqual(res1["data"]["status"], "closed")

        # Customer reopening ticket -> 403 FORBIDDEN (Section 8 Negative Matrix)
        res2 = update_ticket_status(101, "in_progress", user_context=CHARLIE_CONTEXT)
        self.assertFalse(res2.get("success"))
        self.assertEqual(res2["error"]["code"], "FORBIDDEN")

        # Customer closing other's ticket -> 404 NOT_FOUND (Section 8 Negative Matrix)
        res3 = update_ticket_status(102, "closed", user_context=CHARLIE_CONTEXT)
        self.assertFalse(res3.get("success"))
        self.assertEqual(res3["error"]["code"], "NOT_FOUND")

        # Invalid state transition -> 409 CONFLICT
        res4 = update_ticket_status(102, "open", user_context=BOB_CONTEXT)
        self.assertFalse(res4.get("success"))
        self.assertEqual(res4["error"]["code"], "CONFLICT")

    def test_tool5_add_internal_note(self):
        # Customer reading/writing notes -> 403 FORBIDDEN (Section 8 Negative Matrix)
        res1 = add_internal_note(101, "Customer forbidden note", user_context=CHARLIE_CONTEXT)
        self.assertFalse(res1.get("success"))
        self.assertEqual(res1["error"]["code"], "FORBIDDEN")

        # Staff note write -> Success and shape verification
        res2 = add_internal_note(101, "Staff investigation note.", user_context=BOB_CONTEXT)
        self.assertTrue(res2.get("success"))
        data = res2["data"]
        self.assertIn("id", data)
        self.assertIn("ticket_id", data)
        self.assertIn("org_id", data)
        self.assertIn("author_id", data)
        self.assertEqual(data["note"], "Staff investigation note.")

    def test_tool6_issue_refund(self):
        # Staff Privilege Escalation: Bob lacks refund.issue -> 403 FORBIDDEN (Section 8 Negative Matrix)
        res1 = issue_refund(
            invoice_id="inv_org_a_001",
            amount="50.00",
            reason="Customer request",
            idempotency_key="idemp_bob_refund_v3",
            user_context=BOB_CONTEXT,
        )
        self.assertFalse(res1.get("success"))
        self.assertEqual(res1["error"]["code"], "FORBIDDEN")

        # Unapproved refund > $100 -> 403 FORBIDDEN (Section 8 Negative Matrix)
        res2 = issue_refund(
            invoice_id="inv_org_a_001",
            amount="250.00",
            reason="Large unapproved refund",
            idempotency_key="idemp_alice_unapproved_v3",
            approval_token=None,
            user_context=ALICE_CONTEXT,
        )
        self.assertFalse(res2.get("success"))
        self.assertEqual(res2["error"]["code"], "FORBIDDEN")

        # Approved refund > $100 with valid HMAC token -> Success
        hmac_token = generate_approval_hmac(
            invoice_id="inv_org_a_001",
            amount=150.00,
            org_id=ALICE_CONTEXT["org_id"],
            approver_id=ALICE_CONTEXT["user_id"],
        )
        res3 = issue_refund(
            invoice_id="inv_org_a_001",
            amount="150.00",
            reason="Approved refund via HMAC token",
            idempotency_key="idemp_alice_hmac_v3",
            approval_token=hmac_token,
            user_context=ALICE_CONTEXT,
        )
        self.assertTrue(res3.get("success"))
        self.assertEqual(res3["data"]["status"], "partially_refunded")

        # Idempotency check returns cached response
        res3_cached = issue_refund(
            invoice_id="inv_org_a_001",
            amount="150.00",
            reason="Approved refund via HMAC token",
            idempotency_key="idemp_alice_hmac_v3",
            approval_token=hmac_token,
            user_context=ALICE_CONTEXT,
        )
        self.assertTrue(res3_cached.get("success"))
        self.assertEqual(res3_cached["data"]["refund_details"]["idempotency_key"], "idemp_alice_hmac_v3")

        # Single-use consumption: Replaying consumed token -> 403 FORBIDDEN
        res4 = issue_refund(
            invoice_id="inv_org_a_001",
            amount="150.00",
            reason="Attempting reuse of consumed token",
            idempotency_key="idemp_alice_replayed_token_v3",
            approval_token=hmac_token,
            user_context=ALICE_CONTEXT,
        )
        self.assertFalse(res4.get("success"))
        self.assertEqual(res4["error"]["code"], "FORBIDDEN")
        self.assertIn("consumed", res4["error"]["message"])


if __name__ == "__main__":
    unittest.main()
