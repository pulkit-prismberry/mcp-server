"""The 6 Canonical MCP Tools conforming to Team Contract v3.0 Locked."""
from typing import Annotated, Any, Optional, Union
from mcp.server.fastmcp import Context
from pydantic import Field

from services.ticket_service import TicketService
from utils.auth import extract_token_from_mcp_context
from utils.responses import error_response


def get_ticket_details(
    ticket_id: Annotated[Union[str, int], Field(description="Ticket unique identifier (UUID or integer ID).")],
    user_context: Annotated[
        Optional[Union[dict[str, Any], str]],
        Field(default=None, description="Caller user context dictionary (user_id, org_id, role, customer_id) or test alias ('alice', 'bob', 'charlie', 'dave').")
    ] = None,
    session_token: Annotated[
        Optional[str],
        Field(default=None, description="Verified session bearer token (validated via GET /auth/me).")
    ] = None,
    ctx: Optional[Context] = None,
) -> dict[str, Any]:
    """Retrieve complete ticket details.

    Permissions (Section 6.1):
    - Staff with ticket.read:org can view any org ticket.
    - Customer with ticket.read:own can ONLY view tickets matching their customer_id.
    - Mismatches or cross-tenant queries return 404 NOT_FOUND.

    Args:
        ticket_id: UUID or integer ID of the ticket.
        user_context: Authenticated caller context.

    Returns:
        Complete Ticket JSON object or standardized error envelope.
    """
    try:
        try:
            int_id = int(ticket_id)
            if int_id <= 0:
                return error_response("VALIDATION_ERROR", "Ticket ID must be greater than zero.")
        except (ValueError, TypeError):
            pass

        effective_token = session_token or extract_token_from_mcp_context(ctx)
        return TicketService.get_ticket(ticket_id, user_context, session_token=effective_token)
    except Exception as exc:
        return error_response("INTERNAL_ERROR", f"Failed to retrieve ticket: {exc}")


def search_tickets(
    query: Annotated[Optional[str], Field(default=None, description="Search term matched against title and description via substring search.")] = None,
    status: Annotated[Optional[str], Field(default=None, description="Optional ticket status filter ('open', 'in_progress', 'resolved', 'closed').")] = None,
    priority: Annotated[Optional[str], Field(default=None, description="Optional priority filter.")] = None,
    category: Annotated[Optional[str], Field(default=None, description="Optional category filter.")] = None,
    limit: Annotated[Optional[int], Field(default=10, ge=1, le=50, description="Max results to return (default: 10).")] = 10,
    offset: Annotated[Optional[int], Field(default=0, ge=0, description="Pagination offset.")] = 0,
    user_context: Annotated[
        Optional[Union[dict[str, Any], str]],
        Field(default=None, description="Caller context dictionary or test alias.")
    ] = None,
    session_token: Annotated[
        Optional[str],
        Field(default=None, description="Verified session bearer token (validated via GET /auth/me).")
    ] = None,
    ctx: Optional[Context] = None,
) -> dict[str, Any]:
    """Search tickets within the caller's authorized scope (Section 6.2).

    Permissions:
    - Staff with ticket.read:org searches across org tickets.
    - Customer with ticket.read:own searches strictly within their own tickets.

    Args:
        query: Search keywords.
        status: Status filter.
        limit: Max results.
        user_context: Caller context.

    Returns:
        List of matching tickets.
    """
    try:
        return TicketService.search_tickets(
            query=query,
            status=status,
            priority=priority,
            category=category,
            limit=limit or 10,
            offset=offset or 0,
            user_context=user_context,
            session_token=session_token or extract_token_from_mcp_context(ctx),
        )
    except Exception as exc:
        return error_response("INTERNAL_ERROR", f"Failed to search tickets: {exc}")


def create_ticket(
    title: Annotated[Optional[str], Field(default=None, description="Ticket title / headline.")] = None,
    subject: Annotated[Optional[str], Field(default=None, description="Ticket subject alias.")] = None,
    description: Annotated[str, Field(min_length=5, description="Detailed explanation of the issue.")] = "",
    category: Annotated[str, Field(default="general", description="Issue category: 'billing', 'technical', 'account', 'general'.")] = "general",
    priority: Annotated[Optional[str], Field(default="medium", description="Urgency: 'low', 'medium', 'high', 'urgent'.")] = "medium",
    customer_id: Annotated[Optional[str], Field(default=None, description="Target customer UUID (staff only).")] = None,
    invoice_id: Annotated[Optional[str], Field(default=None, description="Optional linked invoice ID.")] = None,
    user_context: Annotated[
        Optional[Union[dict[str, Any], str]],
        Field(default=None, description="Caller context dictionary or test alias.")
    ] = None,
    session_token: Annotated[
        Optional[str],
        Field(default=None, description="Verified session bearer token (validated via GET /auth/me).")
    ] = None,
    ctx: Optional[Context] = None,
) -> dict[str, Any]:
    """Create a new support ticket with status 'open' (Section 6.3).

    Rules:
    - If caller is Customer: customer_id is automatically taken from their JWT; any passed customer_id is ignored.
    - If caller is Staff: requires ticket.write:org; caller may provide customer_id: UUID. Backend validates customer belongs to staff's org_id. If invalid or cross-tenant, returns 404 NOT_FOUND.

    Args:
        title: Summary of issue.
        description: Full description.
        category: billing, technical, account, general.
        priority: low, medium, high, urgent.
        customer_id: Customer UUID if created by staff.
        user_context: Caller context.

    Returns:
        Newly created Ticket object.
    """
    try:
        ticket_title = (title or subject or "").strip()
        if len(ticket_title) < 3:
            return error_response("VALIDATION_ERROR", "Ticket title must be at least 3 characters.")

        return TicketService.create_ticket(
            title=ticket_title,
            description=description,
            category=category,
            priority=priority or "medium",
            customer_id=customer_id,
            user_context=user_context,
            session_token=session_token or extract_token_from_mcp_context(ctx),
        )
    except Exception as exc:
        return error_response("INTERNAL_ERROR", f"Failed to create ticket: {exc}")


def update_ticket_status(
    ticket_id: Annotated[Union[str, int], Field(description="Target ticket UUID or integer ID.")],
    status: Annotated[str, Field(description="New status ('open', 'in_progress', 'resolved', 'closed').")],
    reason: Annotated[Optional[str], Field(default=None, description="Optional transition explanation.")] = None,
    user_context: Annotated[
        Optional[Union[dict[str, Any], str]],
        Field(default=None, description="Caller context dictionary or test alias.")
    ] = None,
    session_token: Annotated[
        Optional[str],
        Field(default=None, description="Verified session bearer token (validated via GET /auth/me).")
    ] = None,
    ctx: Optional[Context] = None,
) -> dict[str, Any]:
    """Update ticket status following the lifecycle state machine (Section 6.4).

    Permissions:
    - Staff with ticket.status:update can perform valid transitions.
    - Customer: Allowed ONLY if updating own ticket from resolved -> closed.
    - Invalid transitions return 409 CONFLICT.

    Args:
        ticket_id: Ticket identifier.
        status: Target status.
        reason: Optional justification.
        user_context: Caller context.

    Returns:
        Updated Ticket object.
    """
    try:
        return TicketService.update_ticket_status(
            ticket_id=ticket_id,
            status=status,
            reason=reason,
            user_context=user_context,
            session_token=session_token or extract_token_from_mcp_context(ctx),
        )
    except Exception as exc:
        return error_response("INTERNAL_ERROR", f"Failed to update ticket status: {exc}")


def add_internal_note(
    ticket_id: Annotated[Union[str, int], Field(description="Target ticket UUID or integer ID.")],
    note: Annotated[str, Field(min_length=1, max_length=5000, description="Internal staff-only note text.")],
    user_context: Annotated[
        Optional[Union[dict[str, Any], str]],
        Field(default=None, description="Caller context dictionary or test alias.")
    ] = None,
    session_token: Annotated[
        Optional[str],
        Field(default=None, description="Verified session bearer token (validated via GET /auth/me).")
    ] = None,
    ctx: Optional[Context] = None,
) -> dict[str, Any]:
    """Add a staff-only whisper note to a ticket (Section 6.5).

    Permissions:
    - Staff with ticket.note:write.
    - Customer -> 403 FORBIDDEN.

    Args:
        ticket_id: Ticket identifier.
        note: Note text body.
        user_context: Caller context.

    Returns:
        JSON object with id, ticket_id, org_id, author_id, note, created_at.
    """
    try:
        return TicketService.add_internal_note(
            ticket_id=ticket_id,
            note=note,
            user_context=user_context,
            session_token=session_token or extract_token_from_mcp_context(ctx),
        )
    except Exception as exc:
        return error_response("INTERNAL_ERROR", f"Failed to add internal note: {exc}")


def issue_refund(
    invoice_id: Annotated[str, Field(description="Invoice UUID / ID to refund.")],
    amount: Annotated[Union[str, float], Field(description="Amount to refund (e.g. '250.00').")],
    reason: Annotated[str, Field(min_length=5, description="Business justification for refund.")],
    idempotency_key: Annotated[str, Field(description="Globally unique idempotency UUID.")],
    approval_token: Annotated[Optional[str], Field(default=None, description="Admin approval token (required if amount > 100.00).")] = None,
    user_context: Annotated[
        Optional[Union[dict[str, Any], str]],
        Field(default=None, description="Caller context dictionary or test alias.")
    ] = None,
    session_token: Annotated[
        Optional[str],
        Field(default=None, description="Verified session bearer token (validated via GET /auth/me).")
    ] = None,
    ctx: Optional[Context] = None,
) -> dict[str, Any]:
    """Execute refund adhering to Section 6.6 defense-in-depth security rules.

    Enforcement:
    1. Idempotency Check FIRST.
    2. Caller must have refund.issue permission.
    3. If amount > 100.00, requires valid approval_token.
    4. Token Validation: 15-minute TTL, single-use, binds invoice_id, amount, org_id, approver_id.
    5. Amount cannot exceed remaining unrefunded invoice balance.

    Args:
        invoice_id: Target invoice.
        amount: Refund amount.
        reason: Justification.
        idempotency_key: Idempotency UUID.
        approval_token: Required if amount > $100.
        user_context: Caller context.

    Returns:
        Updated Invoice object (status: 'refunded' or 'partially_refunded').
    """
    try:
        return TicketService.issue_refund(
            invoice_id=invoice_id,
            amount=amount,
            reason=reason,
            idempotency_key=idempotency_key,
            approval_token=approval_token,
            user_context=user_context,
            session_token=session_token or extract_token_from_mcp_context(ctx),
        )
    except Exception as exc:
        return error_response("INTERNAL_ERROR", f"Failed to execute refund: {exc}")


def check_health() -> dict[str, Any]:
    """Service Health Probe as specified in Section 3.C."""
    return TicketService.check_health()


def check_liveness() -> dict[str, Any]:
    """Liveness probe (GET /health/live) returning {'status': 'alive'} (Section 3.C)."""
    return TicketService.check_liveness()


def check_readiness() -> dict[str, Any]:
    """Readiness probe (GET /health/ready) verifying dependencies (Section 3.C)."""
    return TicketService.check_readiness()


def register_ticket_tools(mcp: Any) -> None:
    """Register all Contract v3.0 Locked canonical tools with the FastMCP server instance."""
    mcp.tool()(get_ticket_details)
    mcp.tool()(search_tickets)
    mcp.tool()(create_ticket)
    mcp.tool()(update_ticket_status)
    mcp.tool()(add_internal_note)
    mcp.tool()(issue_refund)
    mcp.tool()(check_health)
    mcp.tool()(check_liveness)
    mcp.tool()(check_readiness)
