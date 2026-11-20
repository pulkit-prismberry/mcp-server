
from typing import Annotated, Any
from datetime import datetime, timezone

from pydantic import Field
from mcp.server.fastmcp import FastMCP


# Initialize MCP server
mcp = FastMCP("Multi-Tenant Support AI")


# Temporary mock ticket database
# Week 2: Replace this with Tarun's live backend API.

MOCK_TICKETS = {
    105: {
        "ticket_id": 105,
        "subject": "Payment failed",
        "description": "Customer payment was unsuccessful.",
        "status": "open",
        "priority": "high",
        "customer_id": "customer_001",
        "created_at": "2026-11-18T10:30:00Z",
        "updated_at": "2026-11-19T09:15:00Z"
    },
    106: {
        "ticket_id": 106,
        "subject": "Order delivery delayed",
        "description": "Customer has not received the order.",
        "status": "processing",
        "priority": "medium",
        "customer_id": "customer_002",
        "created_at": "2026-11-17T08:00:00Z",
        "updated_at": "2026-11-19T11:00:00Z"
    }
}


def success_response(data: dict) -> dict:
    """Create a standardized successful response."""

    return {
        "success": True,
        "data": data,
        "error": None
    }


def error_response(code: str, message: str) -> dict:
    """Create a standardized error response."""

    return {
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message
        }
    }


@mcp.tool()
def get_ticket_details(
    ticket_id: Annotated[
        int,
        Field(
            gt=0,
            description="Unique positive ID of the support ticket."
        )
    ]
) -> dict[str, Any]:
    """
    Retrieve details of a support ticket using its ticket ID.

    Args:
        ticket_id: Unique ID of the ticket.

    Returns:
        Standardized response containing ticket details
        or an appropriate error.
    """

    try:
        # 1. Validate ticket ID
        if ticket_id <= 0:
            return error_response(
                "VALIDATION_ERROR",
                "Ticket ID must be greater than zero."
            )

        # 2. Retrieve ticket from mock database
        ticket = MOCK_TICKETS.get(ticket_id)

        # 3. Handle missing ticket
        if ticket is None:
            return error_response(
                "NOT_FOUND",
                "Ticket not found."
            )

        # 4. Return successful response
        return success_response(ticket)

    except Exception:
        # Avoid exposing internal exception details
        return error_response(
            "INTERNAL_ERROR",
            "An unexpected error occurred while retrieving the ticket."
        )


if __name__ == "__main__":
    mcp.run()
