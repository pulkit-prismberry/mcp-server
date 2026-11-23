#!/usr/bin/env python3
"""Quick CLI tool to test retrieving, searching, and updating ticket details conforming to Contract v2.0."""
import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.tickets import (
    add_internal_note,
    add_ticket_message,
    create_ticket,
    get_internal_notes,
    get_ticket_details,
    get_ticket_messages,
    issue_refund,
    search_tickets,
    update_ticket_status,
)
from utils.auth import IDENTITIES, normalize_user_context


def main():
    parser = argparse.ArgumentParser(description="Test MCP Ticket tools (Contract v2.0).")
    parser.add_argument("--as-user", "-u", default="bob", choices=["alice", "bob", "charlie", "dave"],
                        help="Caller identity: alice (Admin A), bob (Agent A), charlie (Customer A), dave (Admin B)")
    subparsers = parser.add_subparsers(dest="command", help="Command to test")

    # Get ticket
    get_p = subparsers.add_parser("get", help="Get ticket details by ID")
    get_p.add_argument("ticket_id", type=int, nargs="?", default=101, help="Ticket ID (default: 101)")

    # Search tickets
    search_p = subparsers.add_parser("search", help="Search tickets")
    search_p.add_argument("--query", "-q", type=str, default=None)
    search_p.add_argument("--status", "-s", type=str, default=None)
    search_p.add_argument("--priority", "-p", type=str, default=None)
    search_p.add_argument("--category", "-c", type=str, default=None)
    search_p.add_argument("--limit", "-l", type=int, default=5)

    # Create ticket
    create_p = subparsers.add_parser("create", help="Create ticket")
    create_p.add_argument("subject", type=str)
    create_p.add_argument("description", type=str)
    create_p.add_argument("--category", "-c", default="general")
    create_p.add_argument("--priority", "-p", default="medium")

    # Update status
    update_p = subparsers.add_parser("update-status", help="Update ticket status")
    update_p.add_argument("ticket_id", type=int)
    update_p.add_argument("status", type=str, help="open, in_progress, resolved, closed")
    update_p.add_argument("--reason", "-r", type=str, default=None)

    # Public message
    msg_p = subparsers.add_parser("add-message", help="Post public message to ticket")
    msg_p.add_argument("ticket_id", type=int)
    msg_p.add_argument("body", type=str)
    msg_p.add_argument("--sender-type", "-t", default="support_agent", choices=["customer", "support_agent", "ai_agent", "system"])

    # Get messages
    get_msg_p = subparsers.add_parser("get-messages", help="Get messages for ticket")
    get_msg_p.add_argument("ticket_id", type=int)

    # Internal note
    note_p = subparsers.add_parser("add-note", help="Add staff-only internal note")
    note_p.add_argument("ticket_id", type=int)
    note_p.add_argument("note", type=str)

    # Get notes
    get_note_p = subparsers.add_parser("get-notes", help="Get staff-only internal notes")
    get_note_p.add_argument("ticket_id", type=int)

    # Refund
    refund_p = subparsers.add_parser("refund", help="Issue refund")
    refund_p.add_argument("invoice_id", type=str, help="Invoice ID (e.g. inv_org_a_001)")
    refund_p.add_argument("amount", type=float, help="Amount in USD")
    refund_p.add_argument("reason", type=str, help="Reason")
    refund_p.add_argument("--approval-token", "-t", default=None, help="Required if amount > $100")
    refund_p.add_argument("--idempotency-key", "-k", default="idemp_cli_test_1")

    args = parser.parse_args()
    user_ctx = IDENTITIES[args.as_user]

    print(f"--- MCP Ticket Tool Test (Contract v2.0) ---")
    print(f"Caller Identity: {args.as_user.upper()} | Org: {user_ctx['org_name']} | Role: {user_ctx['role']}\n")

    if args.command == "search":
        res = search_tickets(
            query=args.query,
            status=args.status,
            priority=args.priority,
            category=args.category,
            limit=args.limit,
            user_context=user_ctx,
        )
    elif args.command == "create":
        res = create_ticket(
            subject=args.subject,
            description=args.description,
            category=args.category,
            priority=args.priority,
            user_context=user_ctx,
        )
    elif args.command == "update-status":
        res = update_ticket_status(args.ticket_id, args.status, reason=args.reason, user_context=user_ctx)
    elif args.command == "add-message":
        res = add_ticket_message(args.ticket_id, args.body, sender_type=args.sender_type, user_context=user_ctx)
    elif args.command == "get-messages":
        res = get_ticket_messages(args.ticket_id, user_context=user_ctx)
    elif args.command == "add-note":
        res = add_internal_note(args.ticket_id, args.note, user_context=user_ctx)
    elif args.command == "get-notes":
        res = get_internal_notes(args.ticket_id, user_context=user_ctx)
    elif args.command == "refund":
        res = issue_refund(
            invoice_id=args.invoice_id,
            amount=args.amount,
            reason=args.reason,
            idempotency_key=args.idempotency_key,
            approval_token=args.approval_token,
            user_context=user_ctx,
        )
    else:
        ticket_id = getattr(args, "ticket_id", 101)
        res = get_ticket_details(ticket_id, user_context=user_ctx)

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
