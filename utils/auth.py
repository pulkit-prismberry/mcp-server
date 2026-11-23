"""Authentication utilities, deterministic test identities, and zero-trust token helpers (Contract v2.3 Final)."""
import os
import time
from typing import Any, Optional
import jwt

# ---------------------------------------------------------------------------
# Section 1: Fixed Test Identities & Deterministic UUIDs
# ---------------------------------------------------------------------------

IDENTITIES = {
    "alice": {
        "user_id": "aaaaaaa1-1111-1111-1111-111111111111",
        "customer_id": None,
        "org_id": "11111111-1111-1111-1111-111111111111",
        "org_name": "Org A",
        "role": "Org_Admin",
        "email": "alice@orga.com",
    },
    "bob": {
        "user_id": "bbbbbbb1-1111-1111-1111-111111111111",
        "customer_id": None,
        "org_id": "11111111-1111-1111-1111-111111111111",
        "org_name": "Org A",
        "role": "Support_Agent",
        "email": "bob@orga.com",
    },
    "charlie": {
        "user_id": "ccccccc1-1111-1111-1111-111111111111",
        "customer_id": "ccccccc2-2222-2222-2222-222222222222",
        "org_id": "11111111-1111-1111-1111-111111111111",
        "org_name": "Org A",
        "role": "End_Customer",
        "email": "charlie@customer.com",
    },
    "dave": {
        "user_id": "ddddddd2-2222-2222-2222-222222222222",
        "customer_id": None,
        "org_id": "22222222-2222-2222-2222-222222222222",
        "org_name": "Org B",
        "role": "Org_Admin",
        "email": "dave@orgb.com",
    },
}

ALICE_CONTEXT = IDENTITIES["alice"]
BOB_CONTEXT = IDENTITIES["bob"]
CHARLIE_CONTEXT = IDENTITIES["charlie"]
DAVE_CONTEXT = IDENTITIES["dave"]

# JWT Configuration (Contract Section 2.A & 2.B)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-support-ai-2026-super-secure-key-32bytes")
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "support-ai-backend"
JWT_AUDIENCE = "support-ai-services"

# In-memory single-use approval token tracking (Contract Section 6.6)
CONSUMED_APPROVAL_TOKENS: set[str] = set()


def generate_jwt(user_context: dict[str, Any], exp_seconds: int = 3600) -> str:
    """Generate a compliant JWT bearer token from user context."""
    now = int(time.time())
    payload = {
        "sub": user_context["user_id"],
        "user_id": user_context["user_id"],
        "customer_id": user_context.get("customer_id"),
        "email": user_context["email"],
        "org_id": user_context["org_id"],
        "role": user_context["role"],
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": now + exp_seconds,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> dict[str, Any]:
    """Statelessly verify bearer token with strictly pinned HS256 algorithm (Section 2.A)."""
    payload = jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=["HS256"],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
    )
    return {
        "user_id": payload["user_id"],
        "customer_id": payload.get("customer_id"),
        "org_id": payload["org_id"],
        "role": payload["role"],
        "email": payload["email"],
    }


def generate_approval_token(
    invoice_id: str,
    amount: float,
    org_id: str,
    approver_id: str = "aaaaaaa1-1111-1111-1111-111111111111",
    ttl_seconds: int = 900,
) -> str:
    """Mint an admin approval token binding invoice, amount, and approver (15-min TTL)."""
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


def verify_and_consume_approval_token(
    token: str,
    expected_invoice_id: str,
    expected_amount: float,
    expected_org_id: str,
) -> tuple[bool, Optional[str]]:
    """Verify approval token signature, payload bindings, TTL, and enforce single-use (Section 6.6)."""
    if token in CONSUMED_APPROVAL_TOKENS:
        return False, "Approval token has already been consumed."

    try:
        payload = jwt.decode(
            token,
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

    # Mark as consumed
    CONSUMED_APPROVAL_TOKENS.add(token)
    return True, None


def normalize_user_context(context: Optional[Any] = None) -> dict[str, Any]:
    """Normalize user context; defaults to Bob (Support Agent, Org A) if not provided."""
    if not context:
        return BOB_CONTEXT

    if isinstance(context, str):
        key = context.lower().strip()
        if key in IDENTITIES:
            return IDENTITIES[key]

    if isinstance(context, dict):
        for k in ("alias", "user", "name", "identity", "persona"):
            val = context.get(k)
            if isinstance(val, str) and val.lower().strip() in IDENTITIES:
                return IDENTITIES[val.lower().strip()]

    return {
        "user_id": str(context.get("user_id", BOB_CONTEXT["user_id"])),
        "customer_id": context.get("customer_id"),
        "org_id": str(context.get("org_id", BOB_CONTEXT["org_id"])),
        "role": str(context.get("role", BOB_CONTEXT["role"])),
        "email": str(context.get("email", BOB_CONTEXT["email"])),
    }
