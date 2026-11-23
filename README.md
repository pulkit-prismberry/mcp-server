# Multi-Tenant Support AI - MCP Server

A Model Context Protocol (MCP) server providing AI agents with tools to interact with customer support tickets and ticketing systems.

## Project Structure

```
mcp-server/
├── CHANGELOG.md           # Release history and updates log
├── config.py              # Central configuration & environment variables
├── server.py              # Main FastMCP server entry point
├── tools/                 # MCP Tool definitions (exposed to AI agents)
│   ├── __init__.py        # Tool registration router (`register_tools`)
│   └── tickets.py         # Support ticket tools (e.g. get_ticket_details)
├── services/              # Business logic layer (decouples tools from storage)
│   ├── __init__.py
│   └── ticket_service.py  # Ticket data retrieval & backend abstraction
├── models/                # Pydantic data schemas & contracts
│   ├── __init__.py
│   └── ticket.py          # Ticket models, enums (status, priority)
├── utils/                 # Utility functions & response helpers
│   ├── __init__.py
│   └── responses.py       # Standardized success_response & error_response
├── data/                  # Data directory (mock data and datasets)
│   ├── __init__.py
│   ├── mock_tickets.py    # In-memory mock ticket records
│   └── customer_support_tickets.csv # Support tickets CSV dataset
├── scripts/               # Operational, migration & seeding scripts
│   ├── __init__.py
│   └── seed_db.py         # PostgreSQL schema & CSV migration script
└── tests/                 # Unit and integration test suite
    ├── __init__.py
    ├── test_tools.py      # Tests for MCP tool endpoints & validations
    ├── test_responses.py  # Tests for standard response envelopes
    └── test_services.py   # Tests for service layer business logic
```

---

## Getting Started

### 1. Installation

Install required dependencies:

```bash
pip install -r requirements.txt
```

### 2. Configure PostgreSQL Database

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Update your PostgreSQL connection variables:

```env
PGHOST=localhost
PGPORT=5432
PGDATABASE=support_db
PGUSER=postgres
PGPASSWORD=your_password
PGSCHEMA=support
```

Seed your PostgreSQL database with the ticket dataset:

```bash
python scripts/seed_db.py --csv data/customer_support_tickets.csv
```

### 3. Running the MCP Server

Start the MCP server using:

```bash
python server.py
```

### 4. Running Tests

Run all unit tests using Python's built-in `unittest` runner:

```bash
python -m unittest discover tests
```

Or using `pytest`:

```bash
pytest
```

---

## MCP Tools & Schemas (Contract v2.0)

All tools strictly enforce multi-tenant isolation, customer ownership, and role-based access control (RBAC).

### Test Identities (Contract Section 1)
- **Alice**: `Org_Admin` (Org A, `alice@orga.com`)
- **Bob**: `Support_Agent` (Org A, `bob@orga.com`)
- **Charlie**: `End_Customer` (Org A, `charlie@customer.com`)
- **Dave**: `Org_Admin` (Org B, `dave@orgb.com`)

### Tool Reference
1. **`get_ticket_details(ticket_id, user_context)`**: Returns ticket details. Cross-tenant or cross-customer access returns `404 NOT_FOUND`.
2. **`search_tickets(query, status, priority, category, limit, offset, user_context)`**: Searches tickets within tenant scope.
3. **`create_ticket(subject, description, category, priority, invoice_id, user_context)`**: Creates a ticket for the user's organization.
4. **`update_ticket_status(ticket_id, status, reason, user_context)`**: Updates status (`open`, `in_progress`, `resolved`, `closed`).
5. **`get_ticket_messages(ticket_id, user_context)`**: Returns public dialogue conversation history.
6. **`add_ticket_message(ticket_id, body, sender_type, sender_id, user_context)`**: Posts a public message (`customer`, `support_agent`, `ai_agent`, `system`).
7. **`get_internal_notes(ticket_id, user_context)`**: Staff-only notes (Charlie `End_Customer` -> `403 FORBIDDEN`).
8. **`add_internal_note(ticket_id, note, user_context)`**: Adds staff-only note (Charlie `End_Customer` -> `403 FORBIDDEN`).
9. **`issue_refund(invoice_id, amount, reason, idempotency_key, approval_token, ticket_id, user_context)`**:
   - Only `Org_Admin` (Alice) can execute refunds (Bob -> `403 FORBIDDEN`).
   - If `amount > 100.00`, requires `approval_token`.
   - Verifies remaining unrefunded balance (else `409 CONFLICT`).
   - Idempotency key deduplication.

---

## Adding New Tools

To add a new tool:
1. Define the tool function in `tools/<domain>.py` (e.g. `tools/tickets.py`).
2. Implement any necessary business logic in `services/`.
3. Define request/response Pydantic models in `models/`.
4. Register the tool in `tools/__init__.py` inside `register_tools(mcp)`.
5. Add unit tests under `tests/test_<domain>.py`.
