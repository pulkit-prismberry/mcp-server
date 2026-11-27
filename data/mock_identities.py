"""Deterministic test identities mandated by Team Contract v3.0 Locked (Section 1).

Used strictly for local unit tests, database seeding, and offline dev mode
(`VERIFY_TOKEN_MODE=local`). In production (`VERIFY_TOKEN_MODE=remote`), all
user context is resolved dynamically from the backend `GET /auth/me` endpoint.
"""
from typing import Any

IDENTITIES: dict[str, dict[str, Any]] = {
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

IDENTITIES_BY_USER_ID: dict[str, dict[str, Any]] = {
    identity["user_id"]: identity
    for identity in IDENTITIES.values()
}
