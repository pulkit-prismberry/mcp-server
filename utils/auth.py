"""Authentication utilities, deterministic test identities, and zero-trust token helpers (Contract v3.0 Locked)."""
from contextvars import ContextVar
import hashlib
import hmac
import os
import time
from typing import Any, Optional
import httpx
import jwt

from config import settings
from data.mock_identities import BOB_CONTEXT, IDENTITIES, IDENTITIES_BY_USER_ID

_REQUEST_VERIFIED_CTX: ContextVar[Optional[dict[str, Any]]] = ContextVar(
    "_REQUEST_VERIFIED_CTX",
    default=None,
)


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

    # Legacy permission alias mapping (still permission-based, never role-name-based)
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

    return False


def get_identity_by_uuid(user_id: str) -> Optional[dict[str, Any]]:
    """Look up authoritative user identity profile strictly by user UUID."""
    if not user_id:
        return None
    return IDENTITIES_BY_USER_ID.get(str(user_id).strip())


def get_live_user_context(user_id: str) -> Optional[dict[str, Any]]:
    """Dynamically resolve live user context (org_id, role, permissions, customer_id, email) from live store (Section 2.B & 2.D)."""
    ctx = get_identity_by_uuid(user_id)
    if ctx is not None:
        return ctx
    try:
        from db.ticket_repository import TicketRepository
        return TicketRepository.get_user_context_by_id(str(user_id).strip())
    except Exception:
        return None


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


# JWT Configuration (loaded from config.settings / .env)
JWT_SECRET_KEY = settings.JWT_SECRET_KEY
JWT_ALGORITHM = settings.JWT_ALGORITHM
JWT_ISSUER = settings.JWT_ISSUER
JWT_AUDIENCE = settings.JWT_AUDIENCE

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
    try:
        ctx = normalize_user_context(user_context_or_id)
    except AuthVerificationError as exc:
        return 401, {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": None,
            }
        }

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
        raise AuthVerificationError("Account is disabled")

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
    """Resolve and verify caller context via backend `GET /api/v1/auth/me` (Contract v3.0 Section 2.C)."""
    url = (
        verify_url
        or settings.AUTH_ME_URL
        or settings.AUTH_VERIFY_URL
        or f"{settings.BACKEND_URL.rstrip('/')}/api/v1/auth/me"
    )
    req_timeout = timeout if timeout is not None else settings.VERIFY_TOKEN_TIMEOUT

    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
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
            f"GET /auth/me failed with status {response.status_code}.",
            code="UNAUTHORIZED",
        )

    try:
        data = response.json()
    except Exception as exc:
        raise AuthVerificationError("Malformed JSON from GET /auth/me.") from exc

    # Support either flat Contract v3.0 /auth/me payload or {"data": {...}} / {"user": {...}} envelope
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
    - 'remote': Strictly calls backend GET /auth/me with Authorization: Bearer <token>.
    - 'local': Strictly verifies HS256 Lean JWT locally and resolves live user context.
    - 'auto': Calls GET /auth/me if AUTH_ME_URL / AUTH_VERIFY_URL is configured; otherwise local HS256.
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
        resolved_mode = "remote" if (settings.AUTH_ME_URL or settings.AUTH_VERIFY_URL) else "local"

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
    approver_id: str,
    ttl_seconds: int = 900,
) -> str:
    """Mint an admin approval token binding invoice, amount, org, and approver (15-min TTL) (Section 6.6).
    
    Generates a dual-compatible token (JWT signed with HS256).
    """
    if not approver_id or not str(approver_id).strip():
        raise ValueError("approver_id is required to mint an approval token.")
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
    approver_id: str,
    ttl_seconds: int = 900,
) -> str:
    """Mint signed single-use HMAC token: token = f"{payload}:{HMAC_SHA256(...)}" (Section 6.6)."""
    if not approver_id or not str(approver_id).strip():
        raise ValueError("approver_id is required to mint an approval HMAC.")
    expires_at = int(time.time()) + ttl_seconds
    formatted_amount = f"{round(float(amount), 2):.2f}"
    payload_str = f"{invoice_id}:{formatted_amount}:{org_id}:{approver_id}:{expires_at}"
    sig = hmac.new(
        JWT_SECRET_KEY.encode("utf-8"),
        payload_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload_str}:{sig}"


def _token_sha256(token_str: str) -> str:
    return hashlib.sha256(token_str.encode("utf-8")).hexdigest()


def _is_approval_token_consumed(token_str: str, sig_or_hash: Optional[str] = None, org_id: Optional[str] = None) -> bool:
    if token_str in CONSUMED_APPROVAL_TOKENS:
        return True
    key = sig_or_hash or _token_sha256(token_str)
    if key in CONSUMED_APPROVAL_TOKENS:
        return True
    try:
        from db.ticket_repository import TicketRepository
        return TicketRepository.is_approval_token_consumed(key, org_id=org_id)
    except Exception:
        return False


def _mark_approval_token_consumed(token_str: str, sig_or_hash: Optional[str] = None) -> None:
    CONSUMED_APPROVAL_TOKENS.add(token_str)
    if sig_or_hash:
        CONSUMED_APPROVAL_TOKENS.add(sig_or_hash)


def extract_approval_signature(token: Optional[str]) -> Optional[str]:
    """Extract the signature or SHA-256 hash stored in `audit_logs.details['approval_signature']`."""
    if not token or not str(token).strip():
        return None
    token_str = str(token).strip()
    if not token_str.startswith("ey"):
        dot_parts = token_str.split(".")
        if len(dot_parts) == 3:
            return dot_parts[2]
        colon_parts = token_str.split(":")
        if len(colon_parts) == 6:
            return colon_parts[5]
    return _token_sha256(token_str)


def verify_and_consume_approval_token(
    token: str,
    expected_invoice_id: str,
    expected_amount: float,
    expected_org_id: str,
) -> tuple[bool, Optional[str]]:
    """Verify approval token signature, payload bindings, TTL, and enforce single-use (Section 6.6).

    Supports:
    - Path A: support_ai-backend 3-part dot format `{expires_at}.{approver_id}.{signature}`
    - Path B: Legacy 6-part colon HMAC format `{invoice_id}:{amount}:{org_id}:{approver_id}:{expires_at}:{sig}`
    - Path C: HS256 JWT format (`aud="refund-approval"`)
    """
    if not token or not str(token).strip():
        return False, "Approval token is required."

    token_str = str(token).strip()
    sig_key = extract_approval_signature(token_str)
    if _is_approval_token_consumed(token_str, sig_or_hash=sig_key, org_id=expected_org_id):
        return False, "Approval token has already been consumed."

    # Path A: support_ai-backend 3-part dot format: f"{expires_at}.{approver_id}.{signature}"
    if "." in token_str and not token_str.startswith("ey"):
        dot_parts = token_str.split(".")
        if len(dot_parts) == 3:
            exp_str, approver_id, provided_sig = dot_parts
            now = int(time.time())
            try:
                expires_at = int(exp_str)
                if now > expires_at:
                    return False, "Approval token has expired (15-minute TTL exceeded)."
            except ValueError:
                return False, "Invalid expiry in approval token."

            amt_candidates = {f"{round(float(expected_amount), 2):.2f}", str(expected_amount)}
            matched = False
            for amt_str in amt_candidates:
                payload_str = f"{expected_invoice_id}:{amt_str}:{expected_org_id}:{approver_id}:{expires_at}"
                expected_sig = hmac.new(
                    JWT_SECRET_KEY.encode("utf-8"),
                    payload_str.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                if hmac.compare_digest(expected_sig, provided_sig):
                    matched = True
                    break

            if not matched:
                return False, "Invalid approval token signature or payload mismatch."

            _mark_approval_token_consumed(token_str, sig_or_hash=provided_sig)
            return True, None

    # Path B: Raw HMAC format: f"{invoice_id}:{amount}:{org_id}:{approver_id}:{expires_at}:{sig}"
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

            _mark_approval_token_consumed(token_str, sig_or_hash=provided_sig)
            return True, None

    # Path C: JWT format (aud="refund-approval")
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

    _mark_approval_token_consumed(token_str, sig_or_hash=sig_key)
    return True, None


def normalize_user_context(context: Optional[Any] = None) -> dict[str, Any]:
    """Normalize user context; defaults to Bob (Support Agent, Org A) only when REQUIRE_AUTH_CONTEXT is False."""
    if not context:
        if settings.REQUIRE_AUTH_CONTEXT:
            raise AuthVerificationError(
                "Authenticated user session context (user_id, org_id, role) is required.",
                code="UNAUTHORIZED",
            )
        return dict(BOB_CONTEXT)

    if isinstance(context, str):
        raw = context.strip()
        lower = raw.lower()
        if lower.startswith("bearer ") or raw.count(".") == 2:
            return verify_session_token(raw)
        if lower in IDENTITIES:
            return _validate_verified_context(dict(IDENTITIES[lower]))
        if raw in IDENTITIES_BY_USER_ID:
            return _validate_verified_context(dict(IDENTITIES_BY_USER_ID[raw]))
        raise AuthVerificationError("Unrecognized user context or session token.")

    if isinstance(context, dict):
        # If a session token is embedded inside the dict, verify it strictly
        embedded_token = context.get("session_token") or context.get("access_token") or context.get("token")
        if isinstance(embedded_token, str) and embedded_token.strip():
            return verify_session_token(embedded_token)

        # Check alias shortcuts
        for k in ("alias", "user", "name", "identity", "persona"):
            val = context.get(k)
            if isinstance(val, str) and val.lower().strip() in IDENTITIES:
                return _validate_verified_context(dict(IDENTITIES[val.lower().strip()]))

        # If user_id UUID is known in authoritative store, enrich with authoritative identity
        uid = context.get("user_id") or context.get("sub") or context.get("id")
        if uid and str(uid).strip() in IDENTITIES_BY_USER_ID:
            base = dict(IDENTITIES_BY_USER_ID[str(uid).strip()])
            # allow local overrides if explicitly provided
            for override_key in ("customer_id", "email", "full_name", "is_active", "role", "permissions"):
                if override_key in context and context[override_key] is not None:
                    base[override_key] = context[override_key]
            return _validate_verified_context(base)

        return _validate_verified_context(context)

    raise AuthVerificationError("Invalid user context format.")


def resolve_verified_user_context(
    user_context: Optional[Any] = None,
    session_token: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve and strictly verify caller context from session_token or user_context (MCP-2.1)."""
    cached_ctx = _REQUEST_VERIFIED_CTX.get()
    if cached_ctx is not None:
        return cached_ctx

    if session_token is not None and str(session_token).strip():
        return verify_session_token(str(session_token))

    mode = (settings.VERIFY_TOKEN_MODE or "auto").lower()
    is_remote = mode == "remote" or (mode == "auto" and bool(settings.AUTH_ME_URL or settings.AUTH_VERIFY_URL))
    if is_remote:
        raise AuthVerificationError(
            "A verified Bearer session token (via MCP _meta or Authorization header) is required.",
            code="UNAUTHORIZED",
        )

    return normalize_user_context(user_context)


def extract_token_from_mcp_context(ctx: Optional[Any]) -> Optional[str]:
    """Extract an agent-injected Bearer / session token from FastMCP Context or env (MCP-2.1 Step 3).

    Checks in priority order:
    1. MCP request `_meta` (`authorization`, `Authorization`, `session_token`, `access_token`, `token`).
    2. HTTP request headers when running over StreamableHTTP / SSE (`Authorization`, `x-session-token`).
    3. `MCP_SESSION_TOKEN` environment variable for per-session stdio subprocesses.
    """
    token_keys = ("authorization", "Authorization", "session_token", "access_token", "token")

    if ctx is not None:
        try:
            req_ctx = ctx.request_context
        except Exception:
            req_ctx = None

        if req_ctx is not None:
            meta = getattr(req_ctx, "meta", None)
            if meta is not None:
                for key in token_keys:
                    val = meta.get(key) if isinstance(meta, dict) else getattr(meta, key, None)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
                # Check Pydantic model_extra if meta is a BaseModel with extra="allow"
                extra = getattr(meta, "model_extra", None)
                if isinstance(extra, dict):
                    for key in token_keys:
                        val = extra.get(key)
                        if isinstance(val, str) and val.strip():
                            return val.strip()

            http_req = getattr(req_ctx, "request", None)
            headers = getattr(http_req, "headers", None) if http_req is not None else None
            if headers is not None:
                for hdr in ("authorization", "Authorization", "x-session-token"):
                    val = headers.get(hdr)
                    if isinstance(val, str) and val.strip():
                        return val.strip()

    env_token = os.getenv("MCP_SESSION_TOKEN", "").strip()
    return env_token or None
