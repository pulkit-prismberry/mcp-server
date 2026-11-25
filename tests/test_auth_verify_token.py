"""Unit tests for MCP-2.1 Step 1: /verify-token client & strict session token verification."""
import unittest
from unittest.mock import MagicMock, patch
import httpx

from utils.auth import (
    ALICE_CONTEXT,
    CHARLIE_CONTEXT,
    AuthVerificationError,
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

    @patch("utils.auth.httpx.post")
    def test_verify_token_via_backend_success_flat_and_enveloped(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "user_id": CHARLIE_CONTEXT["user_id"],
                "org_id": CHARLIE_CONTEXT["org_id"],
                "role": "End_Customer",
                "customer_id": CHARLIE_CONTEXT["customer_id"],
                "permissions": ["ticket.read:own"],
            }
        }
        mock_post.return_value = mock_resp

        ctx = verify_token_via_backend("sample_token", verify_url="http://backend.local/verify-token")
        self.assertEqual(ctx["user_id"], CHARLIE_CONTEXT["user_id"])
        self.assertEqual(ctx["org_id"], CHARLIE_CONTEXT["org_id"])
        self.assertEqual(ctx["role"], "End_Customer")
        mock_post.assert_called_once()

    @patch("utils.auth.httpx.post")
    def test_verify_token_via_backend_401_rejected(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": {"message": "Token revoked"}}
        mock_post.return_value = mock_resp

        with self.assertRaises(AuthVerificationError) as err:
            verify_token_via_backend("revoked_token", verify_url="http://backend.local/verify-token")
        self.assertEqual(err.exception.code, "UNAUTHORIZED")
        self.assertIn("revoked", err.exception.message)

    @patch("utils.auth.httpx.post")
    def test_verify_token_via_backend_missing_claims_rejected(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"user_id": "u1"}  # missing org_id and role
        mock_post.return_value = mock_resp

        with self.assertRaises(AuthVerificationError) as err:
            verify_token_via_backend("incomplete_token", verify_url="http://backend.local/verify-token")
        self.assertEqual(err.exception.code, "UNAUTHORIZED")

    @patch("utils.auth.httpx.post")
    def test_verify_token_via_backend_unreachable_raises_503(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        with self.assertRaises(AuthVerificationError) as err:
            verify_token_via_backend("any_token", verify_url="http://backend.local/verify-token")
        self.assertEqual(err.exception.code, "SERVICE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
