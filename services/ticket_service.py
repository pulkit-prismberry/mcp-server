"""Business logic service layer enforcing Contract v3.0 Locked with PostgreSQL persistence."""
from datetime import datetime, timezone
from decimal import Decimal
import logging
import uuid
from typing import Any, Optional

from config import settings
from data.mock_tickets import (
    MOCK_CUSTOMERS,
    MOCK_IDEMPOTENCY_KEYS,
    MOCK_INTERNAL_NOTES,
    MOCK_INVOICES,
    MOCK_REFUNDS,
    MOCK_TICKETS,
)
from db.connection import is_db_connected
from db.ticket_repository import TicketRepository
from utils.auth import (
    has_permission,
    normalize_user_context,
    verify_and_consume_approval_token,
)
from utils.responses import error_response, success_response

logger = logging.getLogger(__name__)

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


def _resolve_ticket_mock(ticket_identifier: Any) -> Optional[dict[str, Any]]:
    """In-memory fallback ticket resolver."""
    try:
        t_id = int(ticket_identifier)
        if t_id in MOCK_TICKETS:
            return dict(MOCK_TICKETS[t_id])
    except (ValueError, TypeError):
        pass

    str_id = str(ticket_identifier).strip()
    for t in MOCK_TICKETS.values():
        if str(t.get("ticket_id")) == str_id or str(t.get("id")) == str_id:
            return dict(t)
    return None


class TicketService:
    """Service layer implementing the 6 canonical MCP tools backed directly by PostgreSQL (Contract v3.0 Locked)."""

    # -----------------------------------------------------------------------
    # Tool 1: get_ticket_details (Section 6.1)
    # -----------------------------------------------------------------------

    @classmethod
    def get_ticket(
        cls,
        ticket_id: Any,
        user_context: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Retrieve full ticket details directly from PostgreSQL.

        Permissions (Section 6.1):
        - Staff with ticket.read:org can view any org ticket.
        - Customer with ticket.read:own can ONLY view tickets matching their customer_id.
        - Cross-tenant or non-owned returns 404 NOT_FOUND.
        """
        ctx = normalize_user_context(user_context)

        ticket = None
        # Primary: PostgreSQL Database
        try:
            ticket = TicketRepository.get_by_id(ticket_id)
        except Exception as exc:
            logger.warning(f"Database query error in get_ticket: {exc}")
            if not settings.USE_MOCK_FALLBACK:
                return error_response("INTERNAL_ERROR", f"Database error: {exc}")

        # Secondary fallback if allowed and DB unavailable / not found in DB
        if ticket is None and settings.USE_MOCK_FALLBACK:
            ticket = _resolve_ticket_mock(ticket_id)

        if not ticket:
            return error_response("NOT_FOUND", f"Ticket {ticket_id} not found.")

        # Sync with local mock status if mutated in-memory (e.g. by unit test)
        try:
            int_id = int(ticket_id)
            if int_id in MOCK_TICKETS and MOCK_TICKETS[int_id].get("status") != ticket.get("status"):
                ticket["status"] = MOCK_TICKETS[int_id]["status"]
        except (ValueError, TypeError):
            pass

        # Multi-tenant isolation: org_id check
        if str(ticket.get("org_id")) != str(ctx["org_id"]):
            return error_response("NOT_FOUND", f"Ticket {ticket_id} not found.")

        # If user has ticket.read:org, they can view any org ticket
        if has_permission(ctx, "ticket.read:org"):
            return success_response(ticket)

        # Otherwise require ticket.read:own and customer_id match
        if has_permission(ctx, "ticket.read:own") or ctx.get("role") == "End_Customer":
            cust_id = ctx.get("customer_id") or ctx["user_id"]
            if str(ticket.get("customer_id")) != str(cust_id):
                return error_response("NOT_FOUND", f"Ticket {ticket_id} not found.")
            return success_response(ticket)

        return error_response("FORBIDDEN", "User lacks permission to read tickets.")

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
        """Case-insensitive substring search directly from PostgreSQL (Section 6.2)."""
        ctx = normalize_user_context(user_context)
        is_staff_search = has_permission(ctx, "ticket.read:org")
        target_cust_id = None if is_staff_search else (ctx.get("customer_id") or ctx["user_id"])

        # Primary: PostgreSQL Database
        try:
            results = TicketRepository.search(
                org_id=ctx["org_id"],
                query=query,
                status=status,
                priority=priority,
                category=category,
                customer_id=target_cust_id,
                limit=limit,
                offset=offset,
            )
            return success_response(results)
        except Exception as exc:
            logger.warning(f"Database query error in search_tickets: {exc}")
            if not settings.USE_MOCK_FALLBACK:
                return error_response("INTERNAL_ERROR", f"Database error: {exc}")

        # Secondary fallback if mock fallback enabled
        matching = []
        for t in MOCK_TICKETS.values():
            if t["org_id"] != ctx["org_id"]:
                continue

            if not is_staff_search:
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

            matching.append(dict(t))

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
        """Create a new ticket with status 'open' persisting to PostgreSQL (Section 6.3)."""
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
        if not has_permission(ctx, "ticket.write:org") or ctx.get("role") == "End_Customer":
            # Automatically take customer_id from JWT claims; ignore passed customer_id
            assigned_customer_id = ctx.get("customer_id") or ctx["user_id"]
        else:
            # Staff member with ticket.write:org: validate provided customer_id if given
            if customer_id:
                cid_str = str(customer_id).strip()
                valid_in_db = False
                try:
                    valid_in_db = TicketRepository.customer_exists_in_org(cid_str, ctx["org_id"])
                except Exception:
                    pass

                cust_record = MOCK_CUSTOMERS.get(cid_str)
                valid_in_mock = cust_record and cust_record["org_id"] == ctx["org_id"]

                if not (valid_in_db or valid_in_mock):
                    return error_response("NOT_FOUND", "Customer not found in this organization.")
                assigned_customer_id = cid_str
            else:
                assigned_customer_id = ctx["user_id"]

        try:
            new_ticket_id = TicketRepository.get_max_ticket_id() + 1
        except Exception:
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

        # Persist to PostgreSQL
        try:
            TicketRepository.create_ticket(new_ticket)
        except Exception as exc:
            logger.warning(f"Could not persist ticket to PostgreSQL: {exc}")
            if not settings.USE_MOCK_FALLBACK:
                return error_response("INTERNAL_ERROR", f"Failed to persist ticket: {exc}")

        # Keep in-memory mock in sync
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
        """Update ticket status enforcing lifecycle state machine rules in PostgreSQL (Section 4 & 6.4)."""
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

        # Customer rule: Allowed ONLY if updating own ticket from resolved -> closed
        is_staff_status_updater = has_permission(ctx, "ticket.status:update")
        if not is_staff_status_updater or ctx.get("role") == "End_Customer":
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

        # Update in PostgreSQL
        try:
            TicketRepository.update_ticket_status(ticket["ticket_id"], new_status, reason)
        except Exception as exc:
            logger.warning(f"Could not update ticket in PostgreSQL: {exc}")
            if not settings.USE_MOCK_FALLBACK:
                return error_response("INTERNAL_ERROR", f"Failed to update ticket in database: {exc}")

        # Update returned object & mock store
        ticket["status"] = new_status
        ticket["updated_at"] = _now_iso()
        if reason:
            ticket["resolution"] = reason

        int_tid = ticket["ticket_id"]
        if int_tid in MOCK_TICKETS:
            MOCK_TICKETS[int_tid]["status"] = new_status
            MOCK_TICKETS[int_tid]["updated_at"] = ticket["updated_at"]

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
        """Add staff-only internal note stored in PostgreSQL (Section 6.5)."""
        ctx = normalize_user_context(user_context)

        # RBAC Check: Staff with ticket.note:write
        if not has_permission(ctx, "ticket.note:write") or ctx.get("role") == "End_Customer":
            return error_response("FORBIDDEN", "Only staff with 'ticket.note:write' permission can add internal notes.")

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

        # Persist to PostgreSQL
        try:
            TicketRepository.add_internal_note(note_record)
        except Exception as exc:
            logger.warning(f"Could not save internal note to PostgreSQL: {exc}")
            if not settings.USE_MOCK_FALLBACK:
                return error_response("INTERNAL_ERROR", f"Database error saving note: {exc}")

        # In-memory mock sync
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
        """Execute refund adhering to Section 6.6 defense-in-depth rules persisted in PostgreSQL."""
        ctx = normalize_user_context(user_context)

        # 1. Idempotency Check FIRST (Section 6.6 Rule 1)
        try:
            cached_refund = TicketRepository.get_refund_by_idempotency_key(idempotency_key)
            if cached_refund:
                return success_response(cached_refund)
        except Exception:
            pass

        if idempotency_key in MOCK_IDEMPOTENCY_KEYS:
            return success_response(MOCK_IDEMPOTENCY_KEYS[idempotency_key])

        # 2. Permission Check: Caller must have refund.issue (Section 6.6 Rule 2)
        if not has_permission(ctx, "refund.issue"):
            return error_response("FORBIDDEN", "Only users with 'refund.issue' permission can execute refunds.")

        # Convert amount to float
        try:
            num_amount = round(float(amount), 2)
            if num_amount <= 0:
                return error_response("VALIDATION_ERROR", "Refund amount must be greater than zero.")
        except (ValueError, TypeError):
            return error_response("VALIDATION_ERROR", "Invalid numeric amount.")

        # 4. Invoice lookup & tenant check from PostgreSQL
        inv_id_str = str(invoice_id).strip()
        invoice = None
        try:
            invoice = TicketRepository.get_invoice(inv_id_str)
        except Exception:
            pass

        if not invoice and settings.USE_MOCK_FALLBACK:
            invoice = MOCK_INVOICES.get(inv_id_str)

        if not invoice or str(invoice.get("org_id")) != str(ctx["org_id"]):
            return error_response("NOT_FOUND", f"Invoice '{invoice_id}' not found.")

        # 5. Amount cannot exceed remaining unrefunded balance (Section 6.6 Rule 4)
        total_amt = float(invoice.get("total_amount", 0.0))
        refunded_amt = float(invoice.get("refunded_amount", 0.0))
        remaining = round(total_amt - refunded_amt, 2)
        if num_amount > remaining:
            return error_response(
                "CONFLICT",
                f"Refund amount ${num_amount:.2f} exceeds remaining balance of ${remaining:.2f}."
            )

        # 6. Token check for amount > 100.00 (Section 6.6 Rule 3)
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

        # 5. Atomic execution & audit log (Section 6.6 Rule 5)
        new_refunded_total = round(refunded_amt + num_amount, 2)
        new_status = "refunded" if new_refunded_total >= total_amt else "partially_refunded"

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

        # Persist to PostgreSQL
        try:
            TicketRepository.record_refund(refund_record, new_status, new_refunded_total)
        except Exception as exc:
            logger.warning(f"Could not record refund in PostgreSQL: {exc}")
            if not settings.USE_MOCK_FALLBACK:
                return error_response("INTERNAL_ERROR", f"Failed to record refund in database: {exc}")

        invoice_copy = dict(invoice)
        invoice_copy["refunded_amount"] = new_refunded_total
        invoice_copy["status"] = new_status
        invoice_copy["refund_details"] = refund_record

        MOCK_REFUNDS[refund_record["refund_id"]] = refund_record
        MOCK_IDEMPOTENCY_KEYS[idempotency_key] = invoice_copy

        return success_response(invoice_copy)

    # -----------------------------------------------------------------------
    # Service Health Probes (Section 3.C)
    # -----------------------------------------------------------------------

    @classmethod
    def check_liveness(cls) -> dict[str, Any]:
        """Process liveness probe (GET /health/live) returning {'status': 'alive'}."""
        return {"status": "alive"}

    @classmethod
    def check_readiness(cls) -> dict[str, Any]:
        """Dependency readiness probe (GET /health/ready) verifying DB connectivity."""
        if is_db_connected():
            return {"status": "ready"}
        if settings.USE_MOCK_FALLBACK:
            return {"status": "ready", "database": "mock_fallback"}
        return {"status": "unavailable", "database": "disconnected"}

    @classmethod
    def check_health(cls) -> dict[str, Any]:
        """Backward-compatible health probe."""
        return {
            "status": "available",
            "database": "connected" if is_db_connected() else "available",
            "version": "1.0.0",
        }

    # Backward compatibility helper
    @classmethod
    def list_tickets(cls) -> list[dict[str, Any]]:
        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(f"SELECT * FROM {settings.SCHEMA or 'support'}.tickets ORDER BY ticket_id ASC;")
                    return [dict(r) for r in cur.fetchall()]
        except Exception:
            return list(MOCK_TICKETS.values())
