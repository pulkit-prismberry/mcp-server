# Changelog

All notable changes to the Multi-Tenant Support AI MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.1.0] - 2026-11-24

### Added
- **PostgreSQL Native Execution**:
  - Purged all legacy Kaggle dataset rows (8,469 records) via `TRUNCATE CASCADE`.
  - Added dedicated database seeding script [scripts/seed_db.py](file:///home/pulkit/Downloads/mcp-server/scripts/seed_db.py) that seeds strictly the 4 hardcoded tickets (101, 102, 201, 202), 2 invoices, verified customer records (Alice, Bob, Charlie, Dave), and initial staff notes.
  - Refactored `TicketRepository` and `TicketService` to query, filter, search, create, and update records directly in PostgreSQL tables (`support.tickets`, `support.ticket_source_data`, `support.invoices`, `support.ticket_internal_notes`, `support.ticket_refunds`).
  - Configured `.env` with `USE_MOCK_FALLBACK=false` to enforce live PostgreSQL database execution.

---

## [3.0.0] - 2026-11-24

### Added
- **Team Contract v3.0 Locked Compliance**:
  - Implemented Section 4.A Canonical Permission Catalog (`ticket.read:own`, `ticket.read:org`, `ticket.write:own`, `ticket.write:org`, `ticket.status:update`, `ticket.note:read`, `ticket.note:write`, `refund.issue`, `role.manage`, `*`).
  - Added `has_permission(user_context, required_permission)` evaluator enforcing permission-based authorization (permissions, never role names).
  - Added Section 2.C User Context Resolution (`resolve_auth_me` / `GET /auth/me`) supporting `full_name`, `email`, `org_id`, `role`, `permissions`, and `authorized_kb_tiers`. Disabled accounts (`is_active = FALSE`) return `401 UNAUTHORIZED`.
  - Added Section 3.C Health Probes: `check_liveness()` (`/health/live`) returning `{"status": "alive"}` and `check_readiness()` (`/health/ready`) returning `{"status": "ready"}`).
  - Added dual HMAC-SHA256 and HS256 JWT approval token support for Section 6.6 HITL refunds.
  - Added comprehensive `tests/test_contract_v3_0.py` covering Section 1 identities, Section 2 lean JWTs, Section 3 health probes, Section 4 canonical permissions, and Section 8 negative test matrix (57 tests total passing).

### Changed
- Refactored `tools/tickets.py` to route directly to `TicketService` without intermediary middleware layers, preserving clean schemas and zero-overhead execution.
- Updated `DEVELOPER_NOTES.md` with complete Contract v3.0 Locked specifications, diagrams, request flows, and test matrices.

---

## [2.3.0] - 2026-11-23

### Added
- Team Contract v2.3 Final compliance with fixed deterministic UUIDs for Alice, Bob, Charlie, and Dave.
- Lean JWT authentication with HS256 algorithm pinning and live context resolution.
- Defense-in-depth refund flow with single-use approval tokens.
- Unit test suite (`tests/test_contract_v2_3.py`) and live MCP stdio client test (`scripts/test_mcp_client.py`).

---

## [2.0.0] - 2026-11-22

### Added
- Initial 6 canonical MCP tools for multi-tenant support ticket management.
- PostgreSQL database integration with dual-path query support (normalized tables and flat fallback).
- Mock data stores for local development and offline testing.
