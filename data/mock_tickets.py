"""Deterministic mock data conforming to Contract v2.3 Final."""
from typing import Any
from data.mock_identities import IDENTITIES

ORG_A_ID = IDENTITIES["alice"]["org_id"]
ORG_B_ID = IDENTITIES["dave"]["org_id"]

CHARLIE_USER_ID = IDENTITIES["charlie"]["user_id"]
CHARLIE_CUSTOMER_ID = IDENTITIES["charlie"]["customer_id"]
DAVE_USER_ID = IDENTITIES["dave"]["user_id"]

# Valid customer records per organization (Section 6.3)
MOCK_CUSTOMERS = {
    CHARLIE_CUSTOMER_ID: {
        "customer_id": CHARLIE_CUSTOMER_ID,
        "org_id": ORG_A_ID,
        "name": "Charlie Customer",
        "email": "charlie@customer.com",
    },
    "other_cust_2222-2222-2222-222222222222": {
        "customer_id": "other_cust_2222-2222-2222-222222222222",
        "org_id": ORG_A_ID,
        "name": "Second Customer Org A",
        "email": "second@orga.com",
    },
    "cust_b_3333-3333-3333-333333333333": {
        "customer_id": "cust_b_3333-3333-3333-333333333333",
        "org_id": ORG_B_ID,
        "name": "Customer Org B",
        "email": "custb@orgb.com",
    },
}

# Tickets conforming to Contract v2.3
# Section 6.1: Complete Ticket JSON object
MOCK_TICKETS = {
    101: {
        "ticket_id": 101,
        "id": "10111111-1111-1111-1111-111111111111",
        "org_id": ORG_A_ID,
        "customer_id": CHARLIE_CUSTOMER_ID,
        "title": "Subscription renewal overcharge",
        "subject": "Subscription renewal overcharge",
        "description": "Customer was overcharged on annual renewal.",
        "category": "billing",
        "priority": "high",
        "status": "open",
        "invoice_id": "inv_org_a_001",
        "resolution": None,
        "created_at": "2026-11-20T10:00:00Z",
        "updated_at": "2026-11-20T10:00:00Z",
    },
    102: {
        "ticket_id": 102,
        "id": "10222222-2222-2222-2222-222222222222",
        "org_id": ORG_A_ID,
        "customer_id": "other_cust_2222-2222-2222-222222222222",
        "title": "SSO authentication failure",
        "subject": "SSO authentication failure",
        "description": "Internal identity provider SAML failure.",
        "category": "technical",
        "priority": "urgent",
        "status": "in_progress",
        "invoice_id": None,
        "resolution": None,
        "created_at": "2026-11-21T09:00:00Z",
        "updated_at": "2026-11-21T11:00:00Z",
    },
    201: {
        "ticket_id": 201,
        "id": "20111111-1111-1111-1111-111111111111",
        "org_id": ORG_B_ID,
        "customer_id": "cust_b_3333-3333-3333-333333333333",
        "title": "Org B Custom Domain TLS setup",
        "subject": "Org B Custom Domain TLS setup",
        "description": "Requesting TLS cert configuration for custom domain.",
        "category": "account",
        "priority": "medium",
        "status": "open",
        "invoice_id": "inv_org_b_001",
        "resolution": None,
        "created_at": "2026-11-22T08:00:00Z",
        "updated_at": "2026-11-22T08:00:00Z",
    },
}

# Invoices (Section 6.6)
MOCK_INVOICES = {
    "inv_org_a_001": {
        "invoice_id": "inv_org_a_001",
        "id": "inv_org_a_001",
        "org_id": ORG_A_ID,
        "customer_id": CHARLIE_CUSTOMER_ID,
        "total_amount": 500.00,
        "refunded_amount": 0.00,
        "status": "paid",
        "created_at": "2026-11-01T12:00:00Z",
    },
    "inv_org_b_001": {
        "invoice_id": "inv_org_b_001",
        "id": "inv_org_b_001",
        "org_id": ORG_B_ID,
        "customer_id": "cust_b_3333-3333-3333-333333333333",
        "total_amount": 300.00,
        "refunded_amount": 0.00,
        "status": "paid",
        "created_at": "2026-11-05T12:00:00Z",
    },
}

# Internal notes & refund audit stores
MOCK_INTERNAL_NOTES: dict[Any, list[dict]] = {
    101: [
        {
            "id": "note_001",
            "ticket_id": "10111111-1111-1111-1111-111111111111",
            "org_id": ORG_A_ID,
            "author_id": IDENTITIES["bob"]["user_id"],
            "note": "Verified duplicate charge. Awaiting Org_Admin approval.",
            "created_at": "2026-11-20T10:15:00Z",
        }
    ]
}

MOCK_REFUNDS: dict[str, dict] = {}
MOCK_IDEMPOTENCY_KEYS: dict[str, dict] = {}
