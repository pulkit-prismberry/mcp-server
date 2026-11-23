"""Tools package initialization and tool registration router (Contract v2.3 Final)."""
from typing import Any
from tools.tickets import (
    add_internal_note,
    check_health,
    create_ticket,
    get_ticket_details,
    issue_refund,
    register_ticket_tools,
    search_tickets,
    update_ticket_status,
)


def register_tools(mcp: Any) -> None:
    """Register all Contract v2.3 Final tools with the FastMCP server instance."""
    register_ticket_tools(mcp)


__all__ = [
    "register_tools",
    "get_ticket_details",
    "search_tickets",
    "create_ticket",
    "update_ticket_status",
    "add_internal_note",
    "issue_refund",
    "check_health",
    "register_ticket_tools",
]

