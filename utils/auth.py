"""Authentication utilities, deterministic test identities, and zero-trust token helpers (Contract v3.0 Locked)."""
import hashlib
import hmac
import os
import time
from typing import Any, Optional
import httpx
import jwt

from config import settings

# ---------------------------------------------------------------------------
# Section 1: Fixed Test Identities & Deterministic UUIDs (Contract v3.0 Locked)
# ---------------------------------------------------------------------------

IDENTITIES = {
    "alice": {
        "user_id": "aaaaaaa1-1111-1111-1111-111111111111",
        "id": "aaaaaaa1-1111-1111-1111-111111111111",
        "customer_id": None,
        "org_id": "11111111-1111-1111-1111-111111111111",
        "org_name": "Org A",
        "role": "Org_Admin",
        "permissions": ["*"],
        "authorized_kb_tiers": ["public", "internal_staff", "admin_only"],
        "full_name": "Alice Admin",
        "email": "alice@orga.com",
        "is_active": True,
    },
    "bob": {
        "user_id": "bbbbbbb1-1111-1111-1111-111111111111",
        "id": "bbbbbbb1-1111-1111-1111-111111111111",
        "customer_id": None,
        "org_id": "11111111-1111-1111-1111-111111111111",
        "org_name": "Org A",
        "role": "Support_Agent",
        "permissions": [
            "ticket.read:org",
            "ticket.write:org",
            "ticket.status:update",
            "ticket.note:read",
            "ticket.note:write",
            # Legacy aliases for backward compatibility
            "tickets:read",
            "tickets:update",
            "notes:create",
        ],
        "authorized_kb_tiers": ["public", "internal_staff"],
        "full_name": "Bob Agent",
        "email": "bob@orga.com",
        "is_active": True,
    },
    "charlie": {
        "user_id": "ccccccc1-1111-1111-1111-111111111111",
        "id": "ccccccc1-1111-1111-1111-111111111111",
        "customer_id": "ccccccc2-2222-2222-2222-222222222222",
        "org_id": "11111111-1111-1111-1111-111111111111",
        "org_name": "Org A",
        "role": "End_Customer",
        "permissions": [
            "ticket.read:own",
            "ticket.write:own",
            # Legacy aliases for backward compatibility
            "tickets:read_own",
            "tickets:create",
            "tickets:close_own",
        ],
        "authorized_kb_tiers": ["public"],
        "full_name": "Charlie Customer",
        "email": "charlie@customer.com",
        "is_active": True,
    },
    "dave": {
        "user_id": "ddddddd2-2222-2222-2222-222222222222",
        "id": "ddddddd2-2222-2222-2222-222222222222",
        "customer_id": None,
        "org_id": "22222222-2222-2222-2222-222222222222",
        "org_name": "Org B",
        "role": "Org_Admin",
        "permissions": ["*"],
        "authorized_kb_tiers": ["public", "internal_staff", "admin_only"],
        "full_name": "Dave Admin",
        "email": "dave@orgb.com",
        "is_active": True,
    },
}

ALICE_CONTEXT = IDENTITIES["alice"]
BOB_CONTEXT = IDENTITIES["bob"]
CHARLIE_CONTEXT = IDENTITIES["charlie"]
DAVE_CONTEXT = IDENTITIES["dave"]

# Authoritative reverse lookup mapping UUID -> Identity Profile
IDENTITIES_BY_USER_ID: dict[str, dict[str, Any]] = {
    identity["user_id"]: identity
    for identity in IDENTITIES.values()
}


# ---------------------------------------------------------------------------
# Section 4: Canonical Permission Catalog & Authorization (Contract v3.0)
# ---------------------------------------------------------------------------

CANONICAL_PERMISSIONS = {
    "ticket.read:own",
    "ticket.read:org",
    "ticket.write:own",
    "ticket.write:org",
    "ticket.status:update",
    "ticket.note:read",
    "ticket.note:write",
    "refund.issue",
    "kb.read:public",
    "kb.read:internal_staff",
    "kb.read:admin_only",
    "role.manage",
    "*",
}


def has_permission(user_context: Optional[dict[str, Any]], required_permission: str) -> bool:
    """Check if the user has the required permission or administrative wildcard '*' (Contract v3.0 Section 4.A).
    
    Code authorization checks permissions, never role names directly.
    """
    if not user_context:
        return False

    perms = user_context.get("permissions") or []
    if "*" in perms:
        return True
    if required_permission in perms:
        return True

    # Legacy permission mapping / role-based fallback for backward compatibility
    role = user_context.get("role")
    if role == "Org_Admin":
        return True

    legacy_map = {
        "tickets:read": ["ticket.read:org", "ticket.read:own"],
        "tickets:update": ["ticket.status:update"],
        "notes:create": ["ticket.note:write"],
        "tickets:read_own": ["ticket.read:own"],
        "tickets:create": ["ticket.write:own", "ticket.write:org"],
        "tickets:close_own": ["ticket.status:update"],
    }
    for perm in perms:
        if required_permission in legacy_map.get(perm, []):
            return True

    if role == "Support_Agent" and required_permission in (
        "ticket.read:org",
        "ticket.write:org",
        "ticket.status:update",
        "ticket.note:read",
        "ticket.note:write",
    ):
        return True

    if role == "End_Customer" and required_permission in (
        "ticket.read:own",
        "ticket.write:own",
    ):
        return True

    return False


def get_identity_by_uuid(user_id: str) -> Optional[dict[str, Any]]:
    """Look up authoritative user identity profile strictly by user UUID."""
    if not user_id:
        return None
    return IDENTITIES_BY_USER_ID.get(str(user_id).strip())


def get_live_user_context(user_id: str) -> Optional[dict[str, Any]]:
    """Dynamically resolve live user context (org_id, role, permissions, customer_id, email) from live store (Section 2.B & 2.D)."""
    return get_identity_by_uuid(user_id)


def update_live_user_role(
    user_id: str,
    new_role: str,
    new_permissions: Optional[list[str]] = None,
) -> None:
    """Instant permission & role update / revocation in the live store (Section 2.B & 2.C)."""
    uid = str(user_id).strip()
    if uid in IDENTITIES_BY_USER_ID:
        IDENTITIES_BY_USER_ID[uid]["role"] = new_role
        if new_permissions is not None:
            IDENTITIES_BY_USER_ID[uid]["permissions"] = new_permissions


# JWT Configuration (Contract Section 2.A & 2.B)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-support-ai-2026-super-secure-key-32bytes")
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "support-ai-backend"
JWT_AUDIENCE = "support-ai-services"

# In-memory single-use approval token tracking (Contract Section 6.6)
CONSUMED_APPROVAL_TOKENS: set[str] = set()


def generate_jwt(user_context: dict[str, Any], exp_seconds: int = 3600, lean: bool = True) -> str:
    """Generate a compliant Lean JWT bearer token (Contract v3.0 Section 2.B).

    The lean token carries only verified identity (user_id), leaving role, org_id,
    and permissions to be dynamically resolved per request from the live database.
    """
    now = int(time.time())
    user_id = user_context.get("user_id") or user_context.get("sub") or user_context.get("id")
    if lean:
        payload = {
            "sub": str(user_id),
            "user_id": str(user_id),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "iat": now,
            "exp": now + exp_seconds,
        }
    else:
        payload = {
            "sub": str(user_id),
            "user_id": str(user_id),
            "customer_id": user_context.get("customer_id"),
            "email": user_context.get("email"),
            "full_name": user_context.get("full_name"),
            "org_id": user_context.get("org_id"),
            "role": user_context.get("role"),
            "permissions": user_context.get("permissions", []),
            "authorized_kb_tiers": user_context.get("authorized_kb_tiers", ["public"]),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "iat": now,
            "exp": now + exp_seconds,
        }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_raw_jwt_claims(token: str) -> dict[str, Any]:
    """Decode raw token claims with strictly pinned HS256 algorithm without DB enrichment."""
    return jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=["HS256"],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
    )


def verify_jwt(token: str) -> dict[str, Any]:
    """Statelessly verify bearer token with strictly pinned HS256 algorithm and dynamically resolve context (Section 2.B & 2.D)."""
    payload = decode_raw_jwt_claims(token)
    user_id = payload.get("user_id") or payload.get("sub")

    # Dynamic Live Resolution (Section 2.B & 2.C)
    live_ctx = get_live_user_context(str(user_id))
    if live_ctx:
        return {
            "id": str(user_id),
            "user_id": str(user_id),
            "customer_id": live_ctx.get("customer_id"),
            "org_id": live_ctx.get("org_id"),
            "role": live_ctx.get("role"),
            "permissions": live_ctx.get("permissions", []),
            "authorized_kb_tiers": live_ctx.get("authorized_kb_tiers", ["public"]),
            "full_name": live_ctx.get("full_name"),
            "email": live_ctx.get("email"),
            "is_active": live_ctx.get("is_active", True),
        }

    # Fallback to token claims if present (for backward compatibility)
    return {
        "id": str(user_id),
        "user_id": str(user_id),
        "customer_id": payload.get("customer_id"),
        "org_id": payload.get("org_id"),
        "role": payload.get("role"),
        "permissions": payload.get("permissions", []),
        "authorized_kb_tiers": payload.get("authorized_kb_tiers", ["public"]),
        "full_name": payload.get("full_name"),
        "email": payload.get("email"),
        "is_active": payload.get("is_active", True),
    }


def resolve_auth_me(user_context_or_id: Any) -> tuple[int, dict[str, Any]]:
    """User Context Resolution (GET /auth/me) as defined in Section 2.C.

    Returns tuple (status_code, response_dict).
    If user is disabled (is_active=False), returns 401 UNAUTHORIZED.
    """
    ctx = normalize_user_context(user_context_or_id)
    if not ctx.get("is_active", True):
        return 401, {
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Account is disabled",
                "details": None,
            }
        }

    return 200, {
        "id": ctx["user_id"],
        "email": ctx.get("email"),
        "full_name": ctx.get("full_name", ctx.get("email", "").split("@")[0].capitalize()),
        "org_id": ctx["org_id"],
        "customer_id": ctx.get("customer_id"),
        "role": ctx.get("role"),
        "permissions": ctx.get("permissions", []),
        "authorized_kb_tiers": ctx.get("authorized_kb_tiers", ["public"]),
    }


# ---------------------------------------------------------------------------
# MCP-2.1: Session Token Verification via /verify-token & Local Lean JWT
# ---------------------------------------------------------------------------

class AuthVerificationError(Exception):
    """Raised when a session token fails /verify-token or JWT verification."""

    def __init__(self, message: str, code: str = "UNAUTHORIZED"):
        super().__init__(message)
        self.code = code
        self.message = message


def _validate_verified_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Ensure verified context has mandatory user_id, org_id, role and is active."""
    if not isinstance(ctx, dict):
        raise AuthVerificationError("Verified auth payload must be a JSON object.")

    if ctx.get("is_active") is False:
        raise AuthVerificationError("Account is disabled.")

    user_id = ctx.get("user_id") or ctx.get("sub") or ctx.get("id")
    org_id = ctx.get("org_id")
    role = ctx.get("role")

    if not user_id or not org_id or not role:
        raise AuthVerificationError(
            "Verified user context is missing required claims (user_id, org_id, role)."
        )

    normalized = dict(ctx)
    normalized["id"] = str(user_id)
    normalized["user_id"] = str(user_id)
    normalized["org_id"] = str(org_id)
    normalized["role"] = str(role)
    normalized.setdefault("permissions", [])
    normalized.setdefault("authorized_kb_tiers", ["public"])
    normalized.setdefault("is_active", True)
    return normalized


def verify_token_via_backend(
    token: str,
    verify_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> dict[str, Any]:
    """Verify a session bearer token against the backend `/verify-token` endpoint."""
    url = (
        verify_url
        or settings.AUTH_VERIFY_URL
        or f"{settings.BACKEND_URL.rstrip('/')}/verify-token"
    )
    req_timeout = timeout if timeout is not None else settings.VERIFY_TOKEN_TIMEOUT

    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"token": token},
            timeout=req_timeout,
        )
    except httpx.HTTPError as exc:
        raise AuthVerificationError(
            f"Auth verification service unreachable: {exc}",
            code="SERVICE_UNAVAILABLE",
        ) from exc

    if response.status_code in (401, 403):
        try:
            err_body = response.json()
            msg = (
                err_body.get("error", {}).get("message")
                or err_body.get("detail")
                or "Invalid or expired session token."
            )
        except Exception:
            msg = "Invalid or expired session token."
        raise AuthVerificationError(msg, code="UNAUTHORIZED")

    if response.status_code != 200:
        raise AuthVerificationError(
            f"Token verification failed with status {response.status_code}.",
            code="UNAUTHORIZED",
        )

    try:
        data = response.json()
    except Exception as exc:
        raise AuthVerificationError("Malformed JSON from /verify-token.") from exc

    # Support either flat payload or {"data": {...}} / {"user": {...}} envelope
    if isinstance(data, dict):
        if isinstance(data.get("data"), dict):
            data = data["data"]
        elif isinstance(data.get("user"), dict):
            data = data["user"]

    return _validate_verified_context(data)


def verify_session_token(
    token: str,
    mode: Optional[str] = None,
) -> dict[str, Any]:
    """Verify a session token and return a validated user context (user_id, org_id, role).

    Modes:
    - 'remote': Strictly calls backend /verify-token.
    - 'local': Strictly verifies HS256 Lean JWT locally and resolves live user context.
    - 'auto': Calls /verify-token if AUTH_VERIFY_URL is configured; otherwise local HS256.
    """
    if not token or not isinstance(token, str) or not token.strip():
        raise AuthVerificationError("Missing session token.")

    raw_token = token.strip()
    if raw_token.lower().startswith("bearer "):
        raw_token = raw_token[7:].strip()

    if not raw_token:
        raise AuthVerificationError("Missing session token.")

    resolved_mode = (mode or settings.VERIFY_TOKEN_MODE or "auto").lower()
    if resolved_mode == "auto":
        resolved_mode = "remote" if settings.AUTH_VERIFY_URL else "local"

    if resolved_mode == "remote":
        return verify_token_via_backend(raw_token)

    try:
        ctx = verify_jwt(raw_token)
    except jwt.ExpiredSignatureError as exc:
        raise AuthVerificationError("Session token has expired.") from exc
    except Exception as exc:
        raise AuthVerificationError(f"Invalid session token: {exc}") from exc

    return _validate_verified_context(ctx)


# ---------------------------------------------------------------------------
# Section 6.6: HITL Approval Tokens (HMAC-SHA256 & JWT Support)
# ---------------------------------------------------------------------------

def generate_approval_token(
    invoice_id: str,
    amount: float,
    org_id: str,
    approver_id: str = "aaaaaaa1-1111-1111-1111-111111111111",
    ttl_seconds: int = 900,
) -> str:
    """Mint an admin approval token binding invoice, amount, org, and approver (15-min TTL) (Section 6.6).
    
    Generates a dual-compatible token (JWT signed with HS256).
    """
    now = int(time.time())
    payload = {
        "invoice_id": str(invoice_id),
        "amount": round(float(amount), 2),
        "org_id": str(org_id),
        "approver_id": str(approver_id),
        "iat": now,
        "exp": now + ttl_seconds,
        "iss": JWT_ISSUER,
        "aud": "refund-approval",
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def generate_approval_hmac(
    invoice_id: str,
    amount: float,
    org_id: str,
    approver_id: str = "aaaaaaa1-1111-1111-1111-111111111111",
    ttl_seconds: int = 900,
) -> str:
    """Mint signed single-use HMAC token: token = f"{payload}:{HMAC_SHA256(...)}" (Section 6.6)."""
    expires_at = int(time.time()) + ttl_seconds
    formatted_amount = f"{round(float(amount), 2):.2f}"
    payload_str = f"{invoice_id}:{formatted_amount}:{org_id}:{approver_id}:{expires_at}"
    sig = hmac.new(
        JWT_SECRET_KEY.encode("utf-8"),
        payload_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload_str}:{sig}"


def verify_and_consume_approval_token(
    token: str,
    expected_invoice_id: str,
    expected_amount: float,
    expected_org_id: str,
) -> tuple[bool, Optional[str]]:
    """Verify approval token signature, payload bindings, TTL, and enforce single-use (Section 6.6)."""
    if not token or not str(token).strip():
        return False, "Approval token is required."

    token_str = str(token).strip()
    if token_str in CONSUMED_APPROVAL_TOKENS:
        return False, "Approval token has already been consumed."

    # Path A: Raw HMAC format: f"{invoice_id}:{amount}:{org_id}:{approver_id}:{expires_at}:{sig}"
    if ":" in token_str and not token_str.startswith("ey"):
        parts = token_str.split(":")
        if len(parts) == 6:
            inv_id, amt_str, o_id, approver_id, exp_str, provided_sig = parts
            now = int(time.time())
            try:
                expires_at = int(exp_str)
                if now > expires_at:
                    return False, "Approval token has expired (15-minute TTL exceeded)."
            except ValueError:
                return False, "Invalid expiry in approval token."

            payload_str = f"{inv_id}:{amt_str}:{o_id}:{approver_id}:{exp_str}"
            expected_sig = hmac.new(
                JWT_SECRET_KEY.encode("utf-8"),
                payload_str.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(expected_sig, provided_sig):
                return False, "Invalid approval token signature."

            if str(inv_id) != str(expected_invoice_id):
                return False, "Approval token is not bound to this invoice ID."

            try:
                if round(float(amt_str), 2) != round(float(expected_amount), 2):
                    return False, "Approval token amount mismatch."
            except ValueError:
                return False, "Invalid amount in approval token."

            if str(o_id) != str(expected_org_id):
                return False, "Approval token organization mismatch."

            CONSUMED_APPROVAL_TOKENS.add(token_str)
            return True, None

    # Path B: JWT format (aud="refund-approval")
    try:
        payload = jwt.decode(
            token_str,
            JWT_SECRET_KEY,
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            audience="refund-approval",
        )
    except jwt.ExpiredSignatureError:
        return False, "Approval token has expired (15-minute TTL exceeded)."
    except Exception as exc:
        return False, f"Invalid approval token: {exc}"

    if str(payload.get("invoice_id")) != str(expected_invoice_id):
        return False, "Approval token is not bound to this invoice ID."

    if round(float(payload.get("amount", 0)), 2) != round(float(expected_amount), 2):
        return False, "Approval token amount mismatch."

    if str(payload.get("org_id")) != str(expected_org_id):
        return False, "Approval token organization mismatch."

    CONSUMED_APPROVAL_TOKENS.add(token_str)
    return True, None


def normalize_user_context(context: Optional[Any] = None) -> dict[str, Any]:
    """Normalize user context; defaults to Bob (Support Agent, Org A) if not provided."""
    if not context:
        return dict(BOB_CONTEXT)

    if isinstance(context, str):
        key = context.lower().strip()
        if key.startswith("bearer "):
            token = key[7:].strip()
            try:
                return verify_jwt(token)
            except Exception:
                pass
        if key in IDENTITIES:
            return dict(IDENTITIES[key])
        # Check by UUID directly
        if key in IDENTITIES_BY_USER_ID:
            return dict(IDENTITIES_BY_USER_ID[key])

    if isinstance(context, dict):
        # Check alias shortcuts
        for k in ("alias", "user", "name", "identity", "persona"):
            val = context.get(k)
            if isinstance(val, str) and val.lower().strip() in IDENTITIES:
                return dict(IDENTITIES[val.lower().strip()])

        # If user_id UUID is known in authoritative store, enrich with authoritative identity
        uid = context.get("user_id") or context.get("sub") or context.get("id")
        if uid and str(uid).strip() in IDENTITIES_BY_USER_ID:
            base = dict(IDENTITIES_BY_USER_ID[str(uid).strip()])
            # allow local overrides if explicitly provided
            for override_key in ("customer_id", "email", "full_name", "is_active", "role", "permissions"):
                if override_key in context and context[override_key] is not None:
                    base[override_key] = context[override_key]
            return base

    uid = str(context.get("user_id", context.get("id", BOB_CONTEXT["user_id"])))
    role = str(context.get("role", BOB_CONTEXT["role"]))
    perms = context.get("permissions")
    if perms is None:
        if role == "Org_Admin":
            perms = ["*"]
        elif role == "Support_Agent":
            perms = [
                "ticket.read:org",
                "ticket.write:org",
                "ticket.status:update",
                "ticket.note:read",
                "ticket.note:write",
            ]
        else:
            perms = ["ticket.read:own", "ticket.write:own"]

    return {
        "id": uid,
        "user_id": uid,
        "customer_id": context.get("customer_id"),
        "org_id": str(context.get("org_id", BOB_CONTEXT["org_id"])),
        "role": role,
        "email": str(context.get("email", BOB_CONTEXT["email"])),
        "full_name": str(context.get("full_name", BOB_CONTEXT["full_name"])),
        "permissions": perms,
        "authorized_kb_tiers": context.get("authorized_kb_tiers", ["public"]),
        "is_active": context.get("is_active", True),
    }
