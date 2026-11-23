"""Business logic service layer enforcing Contract v2.3 Final."""
from datetime import datetime, timezone
from decimal import Decimal
import logging
import uuid
from typing import Any, Optional

from data.mock_tickets import (
    MOCK_CUSTOMERS,
    MOCK_IDEMPOTENCY_KEYS,
    MOCK_INTERNAL_NOTES,
    MOCK_INVOICES,
    MOCK_REFUNDS,
    MOCK_TICKETS,
)
from db.connection import is_db_connected
from utils.auth import (
    normalize_user_context,
    verify_and_consume_approval_token,
)
from utils.responses import error_response, success_response

logger = logging.getLogger(__name__)

# State machine rules from Section 4
VALID_STATUSES = {"open", "in_progress", "resolved", "closed"}
VALID_TRANSITIONS = {
    "open": {"in_progress", "closed"},
    "in_progress": {"resolved", "closed"},
    "resolved": {"closed", "in_progress"},
    "closed": {"in_progress"},
}

VALID_CATEGORIES = {"billing", "technical", "account", "general"}
VALID_PRIORITIES = {"low", "medium", "high", "urgent"}


def _now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _resolve_ticket(ticket_identifier: Any) -> Optional[dict[str, Any]]:
    """Resolve ticket by integer ID or string/UUID."""
    # Try direct int lookup
    try:
        t_id = int(ticket_identifier)
        if t_id in MOCK_TICKETS:
            return MOCK_TICKETS[t_id]
    except (ValueError, TypeError):
        pass

    # Try lookup by string UUID or ID match
    str_id = str(ticket_identifier).strip()
    for t in MOCK_TICKETS.values():
        if str(t.get("ticket_id")) == str_id or str(t.get("id")) == str_id:
            return t
    return None


class TicketService:
    """Service layer implementing the 6 canonical MCP tools and security matrix (Contract v2.3 Final)."""

    # -----------------------------------------------------------------------
    # Tool 1: get_ticket_details (Section 6.1)
    # -----------------------------------------------------------------------

    @classmethod
    def get_ticket(
        cls,
        ticket_id: Any,
        user_context: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Retrieve full ticket details.

        Permissions:
        - Staff can view any org ticket.
        - Customer can ONLY view tickets matching their customer_id.
        - Cross-tenant or non-owned returns 404 NOT_FOUND.
        """
        ctx = normalize_user_context(user_context)
        ticket = _resolve_ticket(ticket_id)

        if not ticket:
            return error_response("NOT_FOUND", f"Ticket {ticket_id} not found.")

        # Multi-tenant isolation: org_id check
        if ticket["org_id"] != ctx["org_id"]:
            return error_response("NOT_FOUND", f"Ticket {ticket_id} not found.")

        # End_Customer isolation: customer_id check
        if ctx["role"] == "End_Customer":
            cust_id = ctx.get("customer_id") or ctx["user_id"]
            if ticket.get("customer_id") != cust_id:
                return error_response("NOT_FOUND", f"Ticket {ticket_id} not found.")

        return success_response(ticket)

    # -----------------------------------------------------------------------
    # Tool 2: search_tickets (Section 6.2)
    # -----------------------------------------------------------------------

    @classmethod
    def search_tickets(
        cls,
        query: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        user_context: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Case-insensitive substring search across title and description (Section 6.2)."""
        ctx = normalize_user_context(user_context)
        matching = []

        for t in MOCK_TICKETS.values():
            if t["org_id"] != ctx["org_id"]:
                continue

            if ctx["role"] == "End_Customer":
                cust_id = ctx.get("customer_id") or ctx["user_id"]
                if t.get("customer_id") != cust_id:
                    continue

            if query:
                q = query.lower()
                title_match = q in t.get("title", "").lower() or q in t.get("subject", "").lower()
                desc_match = q in t.get("description", "").lower()
                if not (title_match or desc_match):
                    continue

            if status and t.get("status", "").lower() != status.strip().lower():
                continue

            if priority and t.get("priority", "").lower() != priority.strip().lower():
                continue

            if category and t.get("category", "").lower() != category.strip().lower():
                continue

            matching.append(t)

        results = matching[offset : offset + limit]
        return success_response(results)

    # -----------------------------------------------------------------------
    # Tool 3: create_ticket (Section 6.3)
    # -----------------------------------------------------------------------

    @classmethod
    def create_ticket(
        cls,
        title: str,
        description: str,
        category: str = "general",
        priority: str = "medium",
        customer_id: Optional[str] = None,
        user_context: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Create a new ticket with status 'open' (Section 6.3)."""
        ctx = normalize_user_context(user_context)

        norm_category = category.strip().lower()
        if norm_category not in VALID_CATEGORIES:
            return error_response(
                "VALIDATION_ERROR",
                f"Invalid category. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
            )

        norm_priority = priority.strip().lower()
        if norm_priority not in VALID_PRIORITIES:
            return error_response(
                "VALIDATION_ERROR",
                f"Invalid priority. Must be one of: {', '.join(sorted(VALID_PRIORITIES))}"
            )

        # Rules from Section 6.3:
        if ctx["role"] == "End_Customer":
            # Automatically take customer_id from JWT claims; ignore passed customer_id
            assigned_customer_id = ctx.get("customer_id") or ctx["user_id"]
        else:
            # Staff member: validate provided customer_id if given
            if customer_id:
                cust_record = MOCK_CUSTOMERS.get(str(customer_id).strip())
                if not cust_record or cust_record["org_id"] != ctx["org_id"]:
                    return error_response("NOT_FOUND", "Customer not found in this organization.")
                assigned_customer_id = cust_record["customer_id"]
            else:
                assigned_customer_id = ctx["user_id"]

        new_ticket_id = max(MOCK_TICKETS.keys(), default=100) + 1
        new_uuid = str(uuid.uuid4())
        now = _now_iso()

        new_ticket = {
            "ticket_id": new_ticket_id,
            "id": new_uuid,
            "org_id": ctx["org_id"],
            "customer_id": assigned_customer_id,
            "title": title.strip(),
            "subject": title.strip(),
            "description": description.strip(),
            "category": norm_category,
            "priority": norm_priority,
            "status": "open",
            "invoice_id": None,
            "resolution": None,
            "created_at": now,
            "updated_at": now,
        }

        MOCK_TICKETS[new_ticket_id] = new_ticket
        return success_response(new_ticket)

    # -----------------------------------------------------------------------
    # Tool 4: update_ticket_status (Section 6.4 & Section 4)
    # -----------------------------------------------------------------------

    @classmethod
    def update_ticket_status(
        cls,
        ticket_id: Any,
        status: str,
        reason: Optional[str] = None,
        user_context: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Update ticket status enforcing lifecycle state machine rules (Section 4 & 6.4)."""
        ctx = normalize_user_context(user_context)
        ticket_res = cls.get_ticket(ticket_id, ctx)
        if not ticket_res.get("success"):
            return ticket_res

        ticket = ticket_res["data"]
        current_status = ticket.get("status", "open").lower()
        new_status = status.strip().lower()

        if new_status not in VALID_STATUSES:
            return error_response(
                "VALIDATION_ERROR",
                f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )

        # Customer rule: Customers may ONLY transition their own tickets from resolved -> closed
        if ctx["role"] == "End_Customer":
            if not (current_status == "resolved" and new_status == "closed"):
                return error_response(
                    "FORBIDDEN",
                    "Customers may only transition their own tickets from resolved to closed."
                )

        # State machine transition rule (Section 4)
        allowed_next = VALID_TRANSITIONS.get(current_status, set())
        if new_status not in allowed_next:
            return error_response(
                "CONFLICT",
                f"Invalid status transition from '{current_status}' to '{new_status}'."
            )

        ticket["status"] = new_status
        ticket["updated_at"] = _now_iso()
        return success_response(ticket)

    # -----------------------------------------------------------------------
    # Tool 5: add_internal_note (Section 6.5)
    # -----------------------------------------------------------------------

    @classmethod
    def add_internal_note(
        cls,
        ticket_id: Any,
        note: str,
        user_context: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Add staff-only internal note (Section 6.5). End_Customer -> 403 FORBIDDEN."""
        ctx = normalize_user_context(user_context)

        # RBAC Check: Staff only
        if ctx["role"] == "End_Customer":
            return error_response("FORBIDDEN", "Only Org_Admin and Support_Agent users can add internal notes.")

        ticket_res = cls.get_ticket(ticket_id, ctx)
        if not ticket_res.get("success"):
            return ticket_res

        ticket = ticket_res["data"]
        t_uuid = str(ticket.get("id") or ticket.get("ticket_id"))
        note_id = str(uuid.uuid4())
        now = _now_iso()

        note_record = {
            "id": note_id,
            "ticket_id": t_uuid,
            "org_id": ctx["org_id"],
            "author_id": ctx["user_id"],
            "note": note.strip(),
            "created_at": now,
        }

        key = ticket.get("ticket_id", ticket_id)
        notes = MOCK_INTERNAL_NOTES.setdefault(key, [])
        notes.append(note_record)

        return success_response(note_record)

    # -----------------------------------------------------------------------
    # Tool 6: issue_refund (Section 6.6)
    # -----------------------------------------------------------------------

    @classmethod
    def issue_refund(
        cls,
        invoice_id: str,
        amount: Any,
        reason: str,
        idempotency_key: str,
        approval_token: Optional[str] = None,
        user_context: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Execute refund adhering to Section 6.6 defense-in-depth rules."""
        ctx = normalize_user_context(user_context)

        # 1. Role check: Only Org_Admin allowed
        if ctx["role"] != "Org_Admin":
            return error_response("FORBIDDEN", "Only Org_Admin users can execute refunds.")

        # Convert amount to float
        try:
            num_amount = round(float(amount), 2)
            if num_amount <= 0:
                return error_response("VALIDATION_ERROR", "Refund amount must be greater than zero.")
        except (ValueError, TypeError):
            return error_response("VALIDATION_ERROR", "Invalid numeric amount.")

        # 5. Idempotency deduplication check
        if idempotency_key in MOCK_IDEMPOTENCY_KEYS:
            return success_response(MOCK_IDEMPOTENCY_KEYS[idempotency_key])

        # Invoice lookup & tenant check
        inv_id_str = str(invoice_id).strip()
        invoice = MOCK_INVOICES.get(inv_id_str)
        if not invoice or invoice["org_id"] != ctx["org_id"]:
            return error_response("NOT_FOUND", f"Invoice '{invoice_id}' not found.")

        # 4. Amount cannot exceed remaining unrefunded balance
        remaining = round(invoice["total_amount"] - invoice["refunded_amount"], 2)
        if num_amount > remaining:
            return error_response(
                "CONFLICT",
                f"Refund amount ${num_amount:.2f} exceeds remaining balance of ${remaining:.2f}."
            )

        # 2 & 3. Token check for amount > 100.00
        if num_amount > 100.00:
            if not approval_token or not approval_token.strip():
                return error_response("FORBIDDEN", "Refunds exceeding $100.00 require a valid approval_token.")

            valid, err = verify_and_consume_approval_token(
                token=approval_token,
                expected_invoice_id=inv_id_str,
                expected_amount=num_amount,
                expected_org_id=ctx["org_id"],
            )
            if not valid:
                return error_response("FORBIDDEN", err or "Invalid approval_token.")

        # 6. Atomic execution & audit log
        invoice["refunded_amount"] += num_amount
        invoice["status"] = "refunded" if invoice["refunded_amount"] >= invoice["total_amount"] else "partially_refunded"

        refund_record = {
            "refund_id": str(uuid.uuid4()),
            "invoice_id": inv_id_str,
            "org_id": ctx["org_id"],
            "amount": num_amount,
            "reason": reason.strip(),
            "idempotency_key": idempotency_key,
            "authorized_by": ctx["user_id"],
            "processed_at": _now_iso(),
        }

        invoice_copy = dict(invoice)
        invoice_copy["refund_details"] = refund_record

        MOCK_REFUNDS[refund_record["refund_id"]] = refund_record
        MOCK_IDEMPOTENCY_KEYS[idempotency_key] = invoice_copy

        return success_response(invoice_copy)

    # -----------------------------------------------------------------------
    # Service Health Probe (Section 3.C)
    # -----------------------------------------------------------------------

    @classmethod
    def check_health(cls) -> dict[str, Any]:
        """Service Health Probe as specified in Section 3.C."""
        return {
            "status": "available",
            "database": "connected" if is_db_connected() else "available",
            "version": "1.0.0",
        }

    # Backward compatibility helper
    @classmethod
    def list_tickets(cls) -> list[dict[str, Any]]:
        return list(MOCK_TICKETS.values())
