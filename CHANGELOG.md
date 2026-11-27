# Changelog

All notable changes to the Multi-Tenant Support AI MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.2.2] - 2026-11-26 (Contract v3.0 Audit Fixes)

### Fixed
- **Strict Permission-Only RBAC (`utils/auth.py`)**: Removed role-name fallbacks (`Org_Admin`, `Support_Agent`, `End_Customer`) from `has_permission()` so authorization strictly checks canonical permissions per Contract v3.0 Section 4.A.
- **Remote Mode Spoofing Guard (`utils/auth.py`)**: In `VERIFY_TOKEN_MODE=remote`, `resolve_verified_user_context()` now rejects raw `user_context` aliases and strictly requires a verified `Bearer` session token.
- **Database `SERVICE_UNAVAILABLE` Error Code (`services/ticket_service.py`)**: Replaced `INTERNAL_ERROR` on PostgreSQL failures with `SERVICE_UNAVAILABLE` per Contract v3.0 Section 3.B.
- **Persistent Single-Use Approval Tokens (`db/ticket_repository.py`, `utils/auth.py`, `scripts/seed_db.py`)**: Persisted consumed approval token SHA-256 hashes in `support.consumed_approval_tokens` to prevent replay across server restarts.
- **Section 6.6 Refund Check Order (`services/ticket_service.py`)**: Enforced `approval_token` validation (Rule 3) before remaining balance check (Rule 4).

---

## [3.2.1] - 2026-11-26

### Changed
- **De-hardcoded `utils/auth.py`**:
  - Moved deterministic Contract v3.0 test identities (`IDENTITIES`, `ALICE_CONTEXT`, `BOB_CONTEXT`, `CHARLIE_CONTEXT`, `DAVE_CONTEXT`) out of [utils/auth.py](file:///home/pulkit/Downloads/mcp-server/utils/auth.py) into [data/mock_identities.py](file:///home/pulkit/Downloads/mcp-server/data/mock_identities.py).
  - Moved `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ISSUER`, and `JWT_AUDIENCE` into [config.py](file:///home/pulkit/Downloads/mcp-server/config.py) (`settings`).
  - Removed the hardcoded `approver_id` default UUID from `generate_approval_token()` and `generate_approval_hmac()` in [utils/auth.py](file:///home/pulkit/Downloads/mcp-server/utils/auth.py); `approver_id` is now an explicit required argument.
  - Updated imports in `data/mock_tickets.py`, `scripts/`, and `tests/`.

---

## [3.2.0] - 2026-11-25 (MCP-2.1 Auth Context Propagation Complete)

### Added
- **Auth Context Propagation (Step 3 — Agent Session Token Injection via FastMCP `Context`)**:
  - Added `extract_token_from_mcp_context()` in [utils/auth.py](file:///home/pulkit/Downloads/mcp-server/utils/auth.py) to extract agent-injected `Bearer` / session tokens from MCP request `_meta`, HTTP `Authorization` headers, or `MCP_SESSION_TOKEN`.
  - Wired `ctx: Optional[Context] = None` across all 6 canonical tools in [tools/tickets.py](file:///home/pulkit/Downloads/mcp-server/tools/tickets.py) (automatically hidden from LLM tool schemas by FastMCP).
  - Updated [scripts/test_mcp_client.py](file:///home/pulkit/Downloads/mcp-server/scripts/test_mcp_client.py) to verify unauthenticated `401 UNAUTHORIZED` rejection and Lean JWT injection via MCP `meta` over stdio.
  - Added Step 3 context injection unit tests in [tests/test_auth_verify_token.py](file:///home/pulkit/Downloads/mcp-server/tests/test_auth_verify_token.py).
- **Auth Context Propagation (Step 2 — Strict Tool & Service Enforcement)**:
  - Added `resolve_verified_user_context()` in [utils/auth.py](file:///home/pulkit/Downloads/mcp-server/utils/auth.py) and set `REQUIRE_AUTH_CONTEXT=true` by default in [config.py](file:///home/pulkit/Downloads/mcp-server/config.py).
  - Removed the silent fallback to `BOB_CONTEXT` when `user_context` or `session_token` is missing or when a `Bearer` token is invalid.
  - Added `session_token` parameter and strict `401 UNAUTHORIZED` enforcement across all 6 canonical tools in [tools/tickets.py](file:///home/pulkit/Downloads/mcp-server/tools/tickets.py) and [services/ticket_service.py](file:///home/pulkit/Downloads/mcp-server/services/ticket_service.py).
  - Added Step 2 enforcement tests in [tests/test_auth_verify_token.py](file:///home/pulkit/Downloads/mcp-server/tests/test_auth_verify_token.py).
- **Auth Context Propagation (Step 1 — `/verify-token` Client & Config)**:
  - Added `BACKEND_URL`, `AUTH_ME_URL` (defaulting to `GET /auth/me` per Contract v3.0 Section 2.C), `VERIFY_TOKEN_MODE` (`auto` | `remote` | `local`), `VERIFY_TOKEN_TIMEOUT`, and `REQUIRE_AUTH_CONTEXT` settings in [config.py](file:///home/pulkit/Downloads/mcp-server/config.py).
  - Implemented `AuthVerificationError`, `_validate_verified_context()`, `verify_token_via_backend()` (`GET /auth/me` with `Authorization: Bearer <token>`), and `verify_session_token()` in [utils/auth.py](file:///home/pulkit/Downloads/mcp-server/utils/auth.py) to validate mandatory `user_id`, `org_id`, `role`, and `is_active` claims.
  - Added unit tests in [tests/test_auth_verify_token.py](file:///home/pulkit/Downloads/mcp-server/tests/test_auth_verify_token.py).

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
