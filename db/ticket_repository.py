"""Repository for executing PostgreSQL queries against support_ai_db (public schema + RLS)."""
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import logging
import uuid
from typing import Any, Optional
import psycopg2.extras

from config import settings
from db.connection import get_db_connection, set_db_tenant_context

logger = logging.getLogger(__name__)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert PostgreSQL dates, datetimes, decimals, and UUIDs to JSON-friendly types."""
    serialized = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            serialized[k] = v.isoformat()
        elif isinstance(v, Decimal):
            serialized[k] = float(v)
        elif isinstance(v, uuid.UUID):
            serialized[k] = str(v)
        else:
            serialized[k] = v
    return serialized


def _normalize_ticket_row(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize a ticket row and ensure backward-compatible fields."""
    data = _serialize_row(row)
    if "title" in data and "subject" not in data:
        data["subject"] = data["title"]
    if "id" in data and "ticket_id" not in data:
        data["ticket_id"] = data["id"]
    return data


def _normalize_invoice_row(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize an invoice row and expose both `amount` and `total_amount`."""
    data = _serialize_row(row)
    if "amount" in data and "total_amount" not in data:
        data["total_amount"] = data["amount"]
    if "id" in data and "invoice_id" not in data:
        data["invoice_id"] = data["id"]
    return data


class TicketRepository:
    """Database repository for querying and mutating support_ai-backend PostgreSQL tables."""

    @classmethod
    def get_by_id(cls, ticket_id: Any, org_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Fetch ticket details from PostgreSQL `tickets` table by UUID."""
        schema = settings.SCHEMA or "public"
        str_id = str(ticket_id).strip()

        query = f"""
            SELECT
                t.id,
                t.org_id,
                t.customer_id,
                t.assigned_agent_id,
                t.title,
                t.title AS subject,
                t.description,
                LOWER(t.status) AS status,
                LOWER(t.priority) AS priority,
                LOWER(COALESCE(t.category, 'general')) AS category,
                t.channel,
                t.product_name,
                t.resolution,
                t.csat_rating,
                t.first_response_at,
                t.resolved_at,
                t.created_at,
                t.updated_at,
                c.full_name AS customer_name,
                c.email AS customer_email,
                c.age AS customer_age,
                c.gender AS customer_gender
            FROM {schema}.tickets t
            LEFT JOIN {schema}.customers c ON t.customer_id = c.id
            WHERE t.id::text = %s
            LIMIT 1;
        """

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                set_db_tenant_context(cur, org_id)
                cur.execute(query, (str_id,))
                row = cur.fetchone()
                if row:
                    return _normalize_ticket_row(dict(row))
        return None

    @classmethod
    def search(
        cls,
        org_id: str,
        query: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        customer_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search tickets in PostgreSQL scoped to tenant and optional customer."""
        schema = settings.SCHEMA or "public"

        where_clauses = ["t.org_id = %s"]
        params: list[Any] = [str(org_id)]

        if customer_id:
            where_clauses.append("t.customer_id::text = %s")
            params.append(str(customer_id))

        if query:
            where_clauses.append("(t.title ILIKE %s OR t.description ILIKE %s)")
            params.extend([f"%{query.strip()}%", f"%{query.strip()}%"])

        if status:
            where_clauses.append("LOWER(t.status) = LOWER(%s)")
            params.append(status.strip())

        if priority:
            where_clauses.append("LOWER(t.priority) = LOWER(%s)")
            params.append(priority.strip())

        if category:
            where_clauses.append("LOWER(t.category) = LOWER(%s)")
            params.append(category.strip())

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        select_query = f"""
            SELECT
                t.id,
                t.org_id,
                t.customer_id,
                t.assigned_agent_id,
                t.title,
                t.title AS subject,
                t.description,
                LOWER(t.status) AS status,
                LOWER(t.priority) AS priority,
                LOWER(COALESCE(t.category, 'general')) AS category,
                t.channel,
                t.product_name,
                t.resolution,
                t.csat_rating,
                t.first_response_at,
                t.resolved_at,
                t.created_at,
                t.updated_at,
                c.full_name AS customer_name,
                c.email AS customer_email
            FROM {schema}.tickets t
            LEFT JOIN {schema}.customers c ON t.customer_id = c.id
            {where_sql}
            ORDER BY t.created_at DESC
            LIMIT %s OFFSET %s;
        """

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                set_db_tenant_context(cur, org_id)
                cur.execute(select_query, params + [limit, offset])
                rows = cur.fetchall()
                return [_normalize_ticket_row(dict(r)) for r in rows]

    @classmethod
    def create_ticket(cls, ticket_data: dict[str, Any]) -> dict[str, Any]:
        """Insert a newly created ticket into PostgreSQL `tickets` table."""
        schema = settings.SCHEMA or "public"

        t_uuid = str(ticket_data.get("id") or uuid.uuid4())
        org_id = str(ticket_data["org_id"])
        customer_id = str(ticket_data["customer_id"])
        title = ticket_data.get("title") or ticket_data.get("subject") or ""
        description = ticket_data["description"]
        category = ticket_data.get("category", "general")
        priority = ticket_data.get("priority", "medium")
        status = ticket_data.get("status", "open")
        channel = ticket_data.get("channel", "web")
        product_name = ticket_data.get("product_name")
        now = datetime.now(timezone.utc)
        created_at = ticket_data.get("created_at") or now
        updated_at = ticket_data.get("updated_at") or created_at

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                set_db_tenant_context(cur, org_id)
                cur.execute(
                    f"""
                    INSERT INTO {schema}.tickets (
                        id, org_id, customer_id, title, description,
                        status, priority, category, channel, product_name,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        t_uuid, org_id, customer_id, title, description,
                        status, priority, category, channel, product_name,
                        created_at, updated_at,
                    ),
                )
                conn.commit()

        return ticket_data

    @classmethod
    def update_ticket_status(
        cls,
        ticket_id: Any,
        new_status: str,
        reason: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> bool:
        """Update ticket status and optional resolution/resolved_at in PostgreSQL."""
        schema = settings.SCHEMA or "public"
        str_id = str(ticket_id).strip()
        norm_status = new_status.strip().lower()

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                set_db_tenant_context(cur, org_id)
                if norm_status in ("resolved", "closed"):
                    cur.execute(
                        f"""
                        UPDATE {schema}.tickets
                        SET status = %s,
                            resolution = COALESCE(%s, resolution),
                            resolved_at = CASE WHEN %s = 'resolved' THEN COALESCE(resolved_at, NOW()) ELSE resolved_at END,
                            updated_at = NOW()
                        WHERE id::text = %s;
                        """,
                        (norm_status, reason, norm_status, str_id),
                    )
                else:
                    cur.execute(
                        f"""
                        UPDATE {schema}.tickets
                        SET status = %s,
                            updated_at = NOW()
                        WHERE id::text = %s;
                        """,
                        (norm_status, str_id),
                    )
                conn.commit()
                return cur.rowcount > 0

    @classmethod
    def add_internal_note(cls, note_record: dict[str, Any]) -> bool:
        """Store an internal staff note in PostgreSQL `ticket_notes` table."""
        schema = settings.SCHEMA or "public"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                set_db_tenant_context(cur, note_record["org_id"])
                cur.execute(
                    f"""
                    INSERT INTO {schema}.ticket_notes (
                        id, org_id, ticket_id, author_id, note, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (
                        str(note_record["id"]),
                        str(note_record["org_id"]),
                        str(note_record["ticket_id"]),
                        str(note_record["author_id"]),
                        note_record["note"],
                        note_record.get("created_at") or datetime.now(timezone.utc),
                    ),
                )
                conn.commit()
                return True

    @classmethod
    def get_invoice(cls, invoice_id: str, org_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Retrieve invoice details from PostgreSQL `invoices` table."""
        schema = settings.SCHEMA or "public"
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                set_db_tenant_context(cur, org_id)
                cur.execute(
                    f"SELECT * FROM {schema}.invoices WHERE id::text = %s LIMIT 1;",
                    (str(invoice_id).strip(),),
                )
                row = cur.fetchone()
                if row:
                    return _normalize_invoice_row(dict(row))
        return None

    @classmethod
    def record_refund(
        cls,
        refund_record: dict[str, Any],
        new_invoice_status: str,
        new_refunded_total: float,
    ) -> bool:
        """Atomically update invoice balance/status and write `refund.issue` entry to `audit_logs`."""
        schema = settings.SCHEMA or "public"
        org_id = str(refund_record["org_id"])
        invoice_id = str(refund_record["invoice_id"])
        audit_id = str(refund_record.get("refund_id") or uuid.uuid4())

        details = {
            "amount": f"{float(refund_record['amount']):.2f}",
            "reason": refund_record["reason"],
            "idempotency_key": refund_record["idempotency_key"],
            "approval_signature": refund_record.get("approval_signature"),
            "new_refunded_amount": f"{float(new_refunded_total):.2f}",
            "new_status": new_invoice_status,
            "remaining_balance": f"{float(refund_record.get('remaining_balance', 0.0)):.2f}",
        }

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                set_db_tenant_context(cur, org_id)
                cur.execute(
                    f"""
                    UPDATE {schema}.invoices
                    SET refunded_amount = %s,
                        status = %s,
                        updated_at = NOW()
                    WHERE id::text = %s AND org_id = %s;
                    """,
                    (new_refunded_total, new_invoice_status, invoice_id, org_id),
                )

                cur.execute(
                    f"""
                    INSERT INTO {schema}.audit_logs (
                        id, org_id, actor_id, action, resource_type, resource_id, details, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        audit_id,
                        org_id,
                        str(refund_record["authorized_by"]),
                        "refund.issue",
                        "invoices",
                        invoice_id,
                        json.dumps(details),
                        refund_record.get("processed_at") or datetime.now(timezone.utc),
                    ),
                )
                conn.commit()
                return True

    @classmethod
    def get_refund_by_idempotency_key(
        cls,
        idempotency_key: str,
        org_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Look up past `refund.issue` audit log by idempotency key."""
        schema = settings.SCHEMA or "public"
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                set_db_tenant_context(cur, org_id)
                cur.execute(
                    f"""
                    SELECT
                        a.id AS audit_log_id,
                        a.org_id,
                        a.actor_id AS authorized_by,
                        a.resource_id AS invoice_id,
                        a.details,
                        a.created_at AS processed_at,
                        i.amount AS total_amount,
                        i.status AS invoice_status,
                        i.refunded_amount
                    FROM {schema}.audit_logs a
                    JOIN {schema}.invoices i ON a.resource_id = i.id
                    WHERE a.action = 'refund.issue'
                      AND a.details->>'idempotency_key' = %s
                    LIMIT 1;
                    """,
                    (idempotency_key.strip(),),
                )
                row = cur.fetchone()
                if row:
                    data = _serialize_row(dict(row))
                    details = data.get("details") or {}
                    return {
                        "invoice_id": data["invoice_id"],
                        "id": data["invoice_id"],
                        "org_id": data["org_id"],
                        "total_amount": data["total_amount"],
                        "amount": data["total_amount"],
                        "refunded_amount": data["refunded_amount"],
                        "status": data["invoice_status"],
                        "refund_details": {
                            "refund_id": data["audit_log_id"],
                            "invoice_id": data["invoice_id"],
                            "org_id": data["org_id"],
                            "amount": float(details.get("amount", 0.0)),
                            "reason": details.get("reason", ""),
                            "idempotency_key": details.get("idempotency_key", idempotency_key),
                            "authorized_by": data["authorized_by"],
                            "processed_at": data["processed_at"],
                        },
                    }
        return None

    @classmethod
    def customer_exists_in_org(cls, customer_uuid: str, org_id: str) -> bool:
        """Verify whether customer UUID belongs to tenant org in PostgreSQL `customers`."""
        schema = settings.SCHEMA or "public"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                set_db_tenant_context(cur, org_id)
                cur.execute(
                    f"""
                    SELECT 1 FROM {schema}.customers
                    WHERE id::text = %s AND org_id = %s
                    LIMIT 1;
                    """,
                    (str(customer_uuid).strip(), str(org_id).strip()),
                )
                return cur.fetchone() is not None

    @classmethod
    def is_approval_token_consumed(cls, signature_or_hash: str, org_id: Optional[str] = None) -> bool:
        """Check whether an approval token signature has already been consumed in `audit_logs`."""
        schema = settings.SCHEMA or "public"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                set_db_tenant_context(cur, org_id)
                cur.execute(
                    f"""
                    SELECT 1 FROM {schema}.audit_logs
                    WHERE action = 'refund.issue'
                      AND details->>'approval_signature' = %s
                    LIMIT 1;
                    """,
                    (signature_or_hash,),
                )
                return cur.fetchone() is not None

    @classmethod
    def get_user_context_by_id(cls, user_id: str) -> Optional[dict[str, Any]]:
        """Resolve live user, role, permissions, and customer_id from `support_ai_db`."""
        schema = settings.SCHEMA or "public"
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT
                        u.id,
                        u.id AS user_id,
                        u.email,
                        u.full_name,
                        u.org_id,
                        u.is_active,
                        c.id AS customer_id,
                        r.name AS role,
                        r.permissions
                    FROM {schema}.users u
                    JOIN {schema}.roles r ON u.role_id = r.id
                    LEFT JOIN {schema}.customers c ON c.user_id = u.id
                    WHERE u.id::text = %s
                    LIMIT 1;
                    """,
                    (str(user_id).strip(),),
                )
                row = cur.fetchone()
                if not row:
                    return None
                data = _serialize_row(dict(row))
                perms = data.get("permissions") or []
                if "*" in perms:
                    tiers = ["public", "internal_staff", "admin_only"]
                else:
                    tiers = []
                    if "kb.read:public" in perms:
                        tiers.append("public")
                    if "kb.read:internal_staff" in perms:
                        tiers.append("internal_staff")
                    if "kb.read:admin_only" in perms:
                        tiers.append("admin_only")
                data["authorized_kb_tiers"] = tiers
                return data
