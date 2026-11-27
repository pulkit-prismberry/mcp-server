"""Unit tests for MCP-2.1 Step 1: /verify-token client & strict session token verification."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import httpx

from data.mock_identities import ALICE_CONTEXT, CHARLIE_CONTEXT
from tools.tickets import (
    add_internal_note,
    create_ticket,
    get_ticket_details,
    issue_refund,
    search_tickets,
    update_ticket_status,
)
from utils.auth import (
    AuthVerificationError,
    extract_token_from_mcp_context,
    generate_jwt,
    verify_session_token,
    verify_token_via_backend,
)


class TestMCP21VerifyTokenStep1(unittest.TestCase):
    """Tests for verify_token_via_backend and verify_session_token."""

    def test_verify_session_token_local_valid_lean_jwt(self):
        token = generate_jwt(ALICE_CONTEXT, lean=True)
        ctx = verify_session_token(f"Bearer {token}", mode="local")
        self.assertEqual(ctx["user_id"], ALICE_CONTEXT["user_id"])
        self.assertEqual(ctx["org_id"], ALICE_CONTEXT["org_id"])
        self.assertEqual(ctx["role"], "Org_Admin")

    def test_verify_session_token_rejects_empty_or_invalid(self):
        with self.assertRaises(AuthVerificationError) as err_empty:
            verify_session_token("", mode="local")
        self.assertEqual(err_empty.exception.code, "UNAUTHORIZED")

        with self.assertRaises(AuthVerificationError) as err_bad:
            verify_session_token("Bearer invalid.jwt.token", mode="local")
        self.assertEqual(err_bad.exception.code, "UNAUTHORIZED")

    def test_verify_session_token_rejects_expired(self):
        expired_token = generate_jwt(CHARLIE_CONTEXT, exp_seconds=-10, lean=True)
        with self.assertRaises(AuthVerificationError) as err:
            verify_session_token(expired_token, mode="local")
        self.assertIn("expired", err.exception.message.lower())

    @patch("utils.auth.get_live_user_context")
    def test_verify_session_token_rejects_disabled_user(self, mock_live_ctx):
        disabled = dict(ALICE_CONTEXT)
        disabled["is_active"] = False
        mock_live_ctx.return_value = disabled

        token = generate_jwt(ALICE_CONTEXT, lean=True)
        with self.assertRaises(AuthVerificationError) as err:
            verify_session_token(token, mode="local")
        self.assertIn("disabled", err.exception.message.lower())

    @patch("utils.auth.httpx.get")
    def test_verify_token_via_backend_success_contract_v3_auth_me(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": CHARLIE_CONTEXT["user_id"],
            "email": CHARLIE_CONTEXT["email"],
            "full_name": CHARLIE_CONTEXT["full_name"],
            "org_id": CHARLIE_CONTEXT["org_id"],
            "customer_id": CHARLIE_CONTEXT["customer_id"],
            "role": "End_Customer",
            "permissions": ["ticket.read:own", "ticket.write:own"],
            "authorized_kb_tiers": ["public"],
        }
        mock_get.return_value = mock_resp

        ctx = verify_token_via_backend("sample_token", verify_url="http://backend.local/auth/me")
        self.assertEqual(ctx["user_id"], CHARLIE_CONTEXT["user_id"])
        self.assertEqual(ctx["org_id"], CHARLIE_CONTEXT["org_id"])
        self.assertEqual(ctx["role"], "End_Customer")
        self.assertEqual(ctx["customer_id"], CHARLIE_CONTEXT["customer_id"])
        mock_get.assert_called_once()

    @patch("utils.auth.httpx.get")
    def test_verify_token_via_backend_401_rejected(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": {"code": "UNAUTHORIZED", "message": "Account is disabled", "details": None}}
        mock_get.return_value = mock_resp

        with self.assertRaises(AuthVerificationError) as err:
            verify_token_via_backend("revoked_token", verify_url="http://backend.local/auth/me")
        self.assertEqual(err.exception.code, "UNAUTHORIZED")
        self.assertIn("disabled", err.exception.message.lower())

    @patch("utils.auth.httpx.get")
    def test_verify_token_via_backend_missing_claims_rejected(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "u1"}  # missing org_id and role
        mock_get.return_value = mock_resp

        with self.assertRaises(AuthVerificationError) as err:
            verify_token_via_backend("incomplete_token", verify_url="http://backend.local/auth/me")
        self.assertEqual(err.exception.code, "UNAUTHORIZED")

    @patch("utils.auth.httpx.get")
    def test_verify_token_via_backend_unreachable_raises_503(self, mock_get):
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        with self.assertRaises(AuthVerificationError) as err:
            verify_token_via_backend("any_token", verify_url="http://backend.local/auth/me")
        self.assertEqual(err.exception.code, "SERVICE_UNAVAILABLE")


class TestMCP21ToolEnforcementStep2(unittest.TestCase):
    """Tests for Step 2: Every canonical MCP tool requires verified session context."""

    def test_all_6_tools_reject_missing_auth_with_401(self):
        calls = [
            get_ticket_details(101),
            search_tickets(query="renewal"),
            create_ticket(title="No Auth Ticket", description="Should fail with 401."),
            update_ticket_status(101, "in_progress"),
            add_internal_note(101, "No auth note"),
            issue_refund("inv_org_a_001", "10.00", "No auth refund", "idemp_no_auth"),
        ]
        for res in calls:
            self.assertFalse(res["success"])
            self.assertEqual(res["error"]["code"], "UNAUTHORIZED")

    def test_invalid_session_token_never_falls_back_to_bob(self):
        res1 = get_ticket_details(101, session_token="invalid.jwt.token")
        self.assertFalse(res1["success"])
        self.assertEqual(res1["error"]["code"], "UNAUTHORIZED")

        res2 = get_ticket_details(101, user_context="Bearer invalid.jwt.token")
        self.assertFalse(res2["success"])
        self.assertEqual(res2["error"]["code"], "UNAUTHORIZED")

    def test_incomplete_user_context_dict_rejected_with_401(self):
        res = get_ticket_details(101, user_context={"user_id": "u1"})  # missing org_id and role
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "UNAUTHORIZED")

    def test_valid_session_token_local_jwt_succeeds(self):
        token = generate_jwt(CHARLIE_CONTEXT, lean=True)
        res = get_ticket_details(101, session_token=f"Bearer {token}")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["customer_id"], CHARLIE_CONTEXT["customer_id"])

    @patch("utils.auth.verify_token_via_backend")
    def test_tool_invocation_uses_remote_verify_token_when_configured(self, mock_remote):
        mock_remote.return_value = {
            "id": CHARLIE_CONTEXT["user_id"],
            "user_id": CHARLIE_CONTEXT["user_id"],
            "customer_id": CHARLIE_CONTEXT["customer_id"],
            "org_id": CHARLIE_CONTEXT["org_id"],
            "role": "End_Customer",
            "permissions": ["ticket.read:own"],
            "authorized_kb_tiers": ["public"],
            "is_active": True,
        }
        with patch("utils.auth.settings", MagicMock(VERIFY_TOKEN_MODE="remote", AUTH_ME_URL="", AUTH_VERIFY_URL="")):
            res = get_ticket_details(101, session_token="opaque_agent_session_token")
        self.assertTrue(res["success"])
        mock_remote.assert_called_once_with("opaque_agent_session_token")

    def test_remote_mode_rejects_user_context_alias_without_token(self):
        with patch("utils.auth.settings", MagicMock(VERIFY_TOKEN_MODE="remote", AUTH_ME_URL="", AUTH_VERIFY_URL="")):
            res = get_ticket_details(101, user_context="alice")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "UNAUTHORIZED")


class TestMCP21ContextInjectionStep3(unittest.TestCase):
    """Tests for Step 3: Agent session token injection via FastMCP Context / headers / env."""

    def test_extract_token_from_mcp_meta_dict(self):
        token = generate_jwt(CHARLIE_CONTEXT, lean=True)
        mock_ctx = SimpleNamespace(
            request_context=SimpleNamespace(
                meta={"authorization": f"Bearer {token}"},
                request=None,
            )
        )
        extracted = extract_token_from_mcp_context(mock_ctx)
        self.assertEqual(extracted, f"Bearer {token}")

        res = get_ticket_details(101, ctx=mock_ctx)
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["customer_id"], CHARLIE_CONTEXT["customer_id"])

    def test_extract_token_from_http_headers(self):
        mock_ctx = SimpleNamespace(
            request_context=SimpleNamespace(
                meta=None,
                request=SimpleNamespace(headers={"Authorization": "Bearer http_header_tok"}),
            )
        )
        self.assertEqual(extract_token_from_mcp_context(mock_ctx), "Bearer http_header_tok")

    def test_extract_token_from_env_var(self):
        with patch.dict(os.environ, {"MCP_SESSION_TOKEN": "Bearer env_sess_tok"}):
            self.assertEqual(extract_token_from_mcp_context(None), "Bearer env_sess_tok")

    def test_backend_3part_approval_token_verification_and_replay(self):
        import hashlib
        import hmac
        import time
        from config import settings
        from utils.auth import verify_and_consume_approval_token

        invoice_id = "769a2504-7c6c-5950-88f9-6382cfeafd12"
        amount = "250.00"
        org_id = ALICE_CONTEXT["org_id"]
        approver_id = ALICE_CONTEXT["user_id"]
        expires_at = int(time.time()) + 900

        sign_payload = f"{invoice_id}:{amount}:{org_id}:{approver_id}:{expires_at}"
        sig = hmac.new(
            settings.JWT_SECRET_KEY.encode("utf-8"),
            sign_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        token = f"{expires_at}.{approver_id}.{sig}"

        ok, err = verify_and_consume_approval_token(token, invoice_id, 250.00, org_id)
        self.assertTrue(ok, err)
        self.assertIsNone(err)

        # Replay must be rejected
        ok2, err2 = verify_and_consume_approval_token(token, invoice_id, 250.00, org_id)
        self.assertFalse(ok2)
        self.assertIn("consumed", (err2 or "").lower())


if __name__ == "__main__":
    unittest.main()
