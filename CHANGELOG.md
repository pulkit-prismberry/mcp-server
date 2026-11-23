# Changelog

All notable changes to the **Multi-Tenant Support AI MCP Server** project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Tarun's live backend API integration (Week 2 roadmap).
- Vector embeddings / semantic search integration for customer inquiries.
- Multi-tenant authentication and workspace routing.

---

## [2.3.0] - 2026-11-23

### Added
- **Compliance with Shared Team Contract v2.3 Final**:
  - **Section 1 (Fixed Test Identities)**: Updated test identities with deterministic UUIDs:
    - Charlie (`End_Customer`): `user_id="ccccccc1-1111-1111-1111-111111111111"`, `customer_id="ccccccc2-2222-2222-2222-222222222222"`.
    - Alice (`Org_Admin`, Org A), Bob (`Support_Agent`, Org A), Dave (`Org_Admin`, Org B) with `customer_id=None`.
  - **Section 2 (Zero-Trust JWT)**: Strictly pinned `HS256` verification, stateless in-memory decode via `PyJWT` (<1ms execution).
  - **Section 3 (Standard Error Envelope & Health Probe)**: Implemented standard envelope `{"error": {"code": "...", "message": "...", "details": null}}` and `check_health` tool returning `{"status": "available", "database": "connected", "version": "1.0.0"}`.
  - **Section 4 (State Machine Rules)**: Enforced ticket state machine transitions (`open` -> `in_progress` -> `resolved` -> `closed`), returning `409 CONFLICT` on invalid jumps. Customers can only close their own tickets when resolved.
  - **Section 6 (6 Canonical MCP Tools)**: Replaced auxiliary tools with the 6 canonical tools:
    1. `get_ticket_details` (Anti-enumeration 404 for cross-tenant / non-owned tickets)
    2. `search_tickets` (PostgreSQL `ILIKE` substring search across `title` & `description`)
    3. `create_ticket` (Auto-binds customer JWT claims; validates staff-assigned customers within org)
    4. `update_ticket_status` (Validates state machine transitions)
    5. `add_internal_note` (Staff-only; End_Customer returns `403 FORBIDDEN`)
    6. `issue_refund` (Org_Admin only; refunds >$100 require single-use 15-min cryptographic approval token; checks balance and idempotency key)
    - Plus `check_health` probe.
  - **Section 7 (Kaggle Dataset & External Support Data Mapping)**: Fully mapped external Kaggle CSV columns to relational models and queries:
    - `Ticket Subject` -> `title` / `subject`
    - `Ticket Description` -> `description`
    - `Ticket Type` -> `category`
    - `Ticket Channel` -> `channel` (`chat`, `email`, `web`, `phone`)
    - `Customer Satisfaction Rating` -> `csat_rating` (1 to 5)
    - `First Response Time` & `Time to Resolution` -> `first_response_at` & `resolved_at` (SLA calculation timestamps)
    - `Customer Name`, `Email`, `Age`, `Gender` -> `full_name`, `email`, `age`, `gender`
    - `Product Purchased` & `Date of Purchase` -> `product_name` & `created_at`
  - **Test Suite**: Added `tests/test_contract_v2_3.py` (22 tests) bringing total passing tests to 41.
  - **E2E MCP Stdio Test Client**: Added `scripts/test_mcp_client.py` validating tool discovery and multi-persona execution over live stdio transport.

---

## [2.0.0] - 2026-11-23

### Added
- **Compliance with Shared Team Contract v2.0**:
  - Implemented deterministic test identities for Alice (`Org_Admin`, Org A), Bob (`Support_Agent`, Org A), Charlie (`End_Customer`, Org A), and Dave (`Org_Admin`, Org B).
  - Added JWT token generation & verification utilities conforming to HS256, `iss="support-ai-backend"`, `aud="support-ai-services"` in `utils/auth.py`.
  - Added public dialogue ticket messages tools: `get_ticket_messages` and `add_ticket_message` supporting sender types (`customer`, `support_agent`, `ai_agent`, `system`) with nullable `sender_id` for AI messages.
  - Added `create_ticket` tool scoped to caller tenant.
  - Added `get_internal_notes` tool for staff-only notes.
  - Added defense-in-depth refund security in `issue_refund`:
    - Strict `Org_Admin` role check (Bob `Support_Agent` -> `403 FORBIDDEN`).
    - Requirement for `approval_token` on amounts exceeding $100.00.
    - Idempotency key deduplication.
    - Remaining invoice balance verification.
  - Added comprehensive test suite `tests/test_contract_v2.py` verifying multi-tenant isolation, customer ownership, internal note RBAC, and refund security rules.

### Changed
- **Canonical Enums & Envelopes**:
  - Standardized error response envelope to `{ "error": { "code": "...", "message": "...", "details": null } }`.
  - Aligned ticket statuses to `open`, `in_progress`, `resolved`, `closed`.
  - Aligned priorities to `low`, `medium`, `high`, `urgent`.
  - Aligned categories to `billing`, `technical`, `account`, `general`.
- **Multi-Tenant Isolation**:
  - All tools now enforce caller tenant boundary checks; cross-tenant access returns `404 NOT_FOUND` without leaking resource existence.
  - `End_Customer` can only access their own tickets; other customer tickets in the same org return `404 NOT_FOUND`.

---

## [0.4.1] - 2026-11-23

### Fixed
- **PostgreSQL Ticket Status Persistence**: Fixed `update_ticket_status` to execute SQL transactions updating both `support.tickets` (resolving or inserting `status_id` in `support.ticket_statuses`) and `support.ticket_source_data` with commit.
- **Database Persistence for Notes & Refunds**: Added `TicketRepository.add_internal_note()` and `TicketRepository.issue_refund()` to persist operational notes and refunds directly into PostgreSQL.

---

## [0.4.0] - 2026-11-23

### Added
- **`update_ticket_status` Tool**: Allows moving tickets through lifecycle states (`open`, `processing`, `pending_customer`, `resolved`, `closed`) with optional justification and agent attribution.
- **`add_internal_note` Tool**: Allows appending private, staff-only notes to tickets for internal handoffs, escalation logs, and diagnostic history.
- **`issue_refund` Tool**: Enables authorized monetary refunds linked to support tickets with amount, currency, and business justification validation.
- **Pydantic Schemas**:
  - `UpdateTicketStatusInput`, `UpdateTicketStatusResponse`, `UpdateTicketStatusResultData`.
  - `AddInternalNoteInput`, `AddInternalNoteResponse`, `InternalNote`.
  - `IssueRefundInput`, `IssueRefundResponse`, `IssueRefundResultData`, `RefundStatus`.
- **Unit Tests**: Added 13 new unit tests across all three operational tools, expanding the test suite to 33 passing tests.

---

## [0.3.0] - 2026-11-23

### Added
- **`search_tickets` Tool**: Added full-featured search tool supporting free-text search in subject and description, plus exact filtering by `status`, `priority`, and `customer_email` with pagination (`limit`, `offset`).
- **Pydantic Schemas & Data Contracts** ([models/ticket.py](file:///home/pulkit/Downloads/mcp-server/models/ticket.py)):
  - Input schemas: `GetTicketDetailsInput`, `SearchTicketsInput`.
  - Entity & output schemas: `TicketDetails`, `ErrorDetail`, `GetTicketDetailsResponse`, `SearchTicketsResultData`, `SearchTicketsResponse`.
  - Enums: `TicketStatus` (`open`, `processing`, `pending_customer`, `resolved`, `closed`), `TicketPriority` (`low`, `medium`, `high`, `critical`).
- **Standardized Docstrings**: Added comprehensive, AI-agent-friendly docstrings to both `get_ticket_details` and `search_tickets` documenting purpose, parameter constraints, output payload structures, and error codes.
- **Database Search Queries**: Added `TicketRepository.search()` supporting dynamic PostgreSQL queries across normalized tables (`support.tickets`) and `support.ticket_source_data`.
- **Mock Search Filtering**: Added in-memory filtering fallback in `TicketService.search_tickets()` for offline and local testing.
- **CLI Subcommands**: Extended [scripts/test_tool.py](file:///home/pulkit/Downloads/mcp-server/scripts/test_tool.py) to support both `get` and `search` subcommands (`python scripts/test_tool.py search --query <term>`).
- **Search Unit Tests**: Added unit tests in [tests/test_tools.py](file:///home/pulkit/Downloads/mcp-server/tests/test_tools.py) for query matching, status filtering, priority filtering, and pagination validation (expanding test suite to 20 passing tests).

---

## [0.2.0] - 2026-11-22

### Added
- **Modular Project Structure**:
  - `tools/`: MCP tool definitions and tool registration router (`register_tools`).
  - `services/`: Business logic service layer (`TicketService`) abstracting data access.
  - `models/`: Dedicated Pydantic data schemas and domain models.
  - `utils/`: Standardized response builders (`success_response`, `error_response`).
  - `data/`: Isolated mock datasets and `customer_support_tickets.csv`.
  - `scripts/`: Seeding and CLI test utilities.
  - `tests/`: Automated unit test suite with `unittest` runner.
- **PostgreSQL Database Integration**:
  - `db/connection.py`: Database connection context manager and health check (`is_db_connected`).
  - `db/ticket_repository.py`: Normalized SQL queries with joined dimensions (`support.tickets` + `customers`, `products`, `ticket_types`, `ticket_statuses`, `ticket_priorities`, `ticket_channels`) and fallback to `support.ticket_source_data`.
  - JSON serialization helper for PostgreSQL `date`, `datetime`, and `Decimal` types.
- **Configuration & Environment**:
  - Added [config.py](file:///home/pulkit/Downloads/mcp-server/config.py) for centralized environment variable management (`dotenv` support).
  - Added [.env.example](file:///home/pulkit/Downloads/mcp-server/.env.example) with PostgreSQL connection parameters (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGSCHEMA`, `USE_MOCK_FALLBACK`).
- **Testing & Tooling**:
  - Created [scripts/test_tool.py](file:///home/pulkit/Downloads/mcp-server/scripts/test_tool.py) for instant terminal-based testing without requiring an MCP client.
  - Created [README.md](file:///home/pulkit/Downloads/mcp-server/README.md) with architecture overview, installation guide, and usage instructions.
  - Created [requirements.txt](file:///home/pulkit/Downloads/mcp-server/requirements.txt) with core dependencies (`mcp`, `pydantic`, `pandas`, `psycopg2-binary`, `python-dotenv`).

### Changed
- Refactored [server.py](file:///home/pulkit/Downloads/mcp-server/server.py) from a monolithic script into a clean FastMCP initialization and tool-registration entrypoint.
- Updated [seed_db.py](file:///home/pulkit/Downloads/mcp-server/seed_db.py) to act as a root compatibility wrapper pointing to [scripts/seed_db.py](file:///home/pulkit/Downloads/mcp-server/scripts/seed_db.py).
- Updated [.gitignore](file:///home/pulkit/Downloads/mcp-server/.gitignore) to exclude CSV datasets and test caches.

---

## [0.1.0] - 2026-11-20

### Added
- Initial FastMCP server prototype in a single `server.py` file.
- Initial `get_ticket_details` tool with input validation.
- In-memory `MOCK_TICKETS` dictionary for development.
- Initial `customer_support_tickets.csv` dataset and `seed_db.py` PostgreSQL migration script.
