"""Repository for executing PostgreSQL queries on support ticket tables (Contract v3.0 Locked)."""
from datetime import date, datetime
from decimal import Decimal
import logging
import uuid
from typing import Any, Optional
import psycopg2.extras

from config import settings
from db.connection import get_db_connection

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


class TicketRepository:
    """Database repository for querying and mutating support tickets in PostgreSQL."""

    @classmethod
    def get_by_id(cls, ticket_id: Any) -> Optional[dict[str, Any]]:
        """Fetch ticket details from PostgreSQL by ticket_id or UUID."""
        schema = settings.SCHEMA or "support"

        is_int = False
        int_id = None
        try:
            int_id = int(ticket_id)
            is_int = True
        except (ValueError, TypeError):
            pass

        str_id = str(ticket_id).strip()
        where_cond = "t.ticket_id = %s OR t.id::text = %s"
        params = (int_id if is_int else -1, str_id)

        normalized_query = f"""
            SELECT 
                t.ticket_id,
                COALESCE(t.id::text, t.ticket_id::text) AS id,
                COALESCE(t.org_id::text, c.org_id::text) AS org_id,
                COALESCE(t.customer_uuid, c.customer_uuid, t.customer_id::text) AS customer_id,
                t.subject,
                COALESCE(t.title, t.subject) AS title,
                t.description,
                LOWER(s.status_name) AS status,
                LOWER(p.priority_name) AS priority,
                LOWER(COALESCE(tt.type_name, 'general')) AS category,
                t.invoice_id,
                c.full_name AS customer_name,
                c.email AS customer_email,
                c.age AS customer_age,
                c.gender AS customer_gender,
                prod.product_name AS product_purchased,
                t.purchase_date,
                tt.type_name AS ticket_type,
                ch.channel_name AS ticket_channel,
                t.resolution,
                t.first_response_at,
                t.resolved_at,
                t.satisfaction_rating,
                t.created_at,
                t.updated_at
            FROM {schema}.tickets t
            LEFT JOIN {schema}.customers c ON (t.customer_uuid = c.customer_uuid OR t.customer_id = c.customer_id)
            LEFT JOIN {schema}.products prod ON t.product_id = prod.product_id
            LEFT JOIN {schema}.ticket_types tt ON t.ticket_type_id = tt.ticket_type_id
            LEFT JOIN {schema}.ticket_statuses s ON t.status_id = s.status_id
            LEFT JOIN {schema}.ticket_priorities p ON t.priority_id = p.priority_id
            LEFT JOIN {schema}.ticket_channels ch ON t.channel_id = ch.channel_id
            WHERE {where_cond}
            LIMIT 1;
        """

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                try:
                    cur.execute(normalized_query, params)
                    row = cur.fetchone()
                    if row:
                        return _serialize_row(dict(row))
                except Exception as exc:
                    logger.debug(f"Normalized query failed: {exc}")
                    conn.rollback()

                try:
                    cur.execute(f"""
                    SELECT 
                        ticket_id,
                        COALESCE(id::text, ticket_id::text) AS id,
                        org_id::text AS org_id,
                        COALESCE(customer_id_uuid, customer_name) AS customer_id,
                        ticket_subject AS subject,
                        COALESCE(title, ticket_subject) AS title,
                        ticket_description AS description,
                        LOWER(ticket_status) AS status,
                        LOWER(ticket_priority) AS priority,
                        LOWER(COALESCE(ticket_type, 'general')) AS category,
                        invoice_id,
                        customer_name,
                        customer_email,
                        imported_at AS created_at,
                        updated_at
                    FROM {schema}.ticket_source_data
                    WHERE ticket_id = %s OR id::text = %s
                    LIMIT 1;
                    """, (int_id if is_int else -1, str_id))
                    row = cur.fetchone()
                    if row:
                        return _serialize_row(dict(row))
                except Exception as exc:
                    logger.debug(f"Source query failed: {exc}")
                    conn.rollback()

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
        schema = settings.SCHEMA or "support"

        where_clauses = ["t.org_id = %s"]
        params: list[Any] = [org_id]

        if customer_id:
            where_clauses.append("(t.customer_uuid = %s OR c.customer_uuid = %s)")
            params.extend([customer_id, customer_id])

        if query:
            where_clauses.append("(t.subject ILIKE %s OR t.description ILIKE %s OR t.title ILIKE %s)")
            params.extend([f"%{query}%", f"%{query}%", f"%{query}%"])

        if status:
            where_clauses.append("LOWER(s.status_name) = LOWER(%s)")
            params.append(status.strip())

        if priority:
            where_clauses.append("LOWER(p.priority_name) = LOWER(%s)")
            params.append(priority.strip())

        if category:
            where_clauses.append("LOWER(tt.type_name) = LOWER(%s)")
            params.append(category.strip())

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        select_query = f"""
            SELECT 
                t.ticket_id,
                COALESCE(t.id::text, t.ticket_id::text) AS id,
                COALESCE(t.org_id::text, c.org_id::text) AS org_id,
                COALESCE(t.customer_uuid, c.customer_uuid, t.customer_id::text) AS customer_id,
                t.subject,
                COALESCE(t.title, t.subject) AS title,
                t.description,
                LOWER(s.status_name) AS status,
                LOWER(p.priority_name) AS priority,
                LOWER(COALESCE(tt.type_name, 'general')) AS category,
                t.invoice_id,
                c.full_name AS customer_name,
                c.email AS customer_email,
                t.resolution,
                t.created_at,
                t.updated_at
            FROM {schema}.tickets t
            LEFT JOIN {schema}.customers c ON (t.customer_uuid = c.customer_uuid OR t.customer_id = c.customer_id)
            LEFT JOIN {schema}.ticket_types tt ON t.ticket_type_id = tt.ticket_type_id
            LEFT JOIN {schema}.ticket_statuses s ON t.status_id = s.status_id
            LEFT JOIN {schema}.ticket_priorities p ON t.priority_id = p.priority_id
            {where_sql}
            ORDER BY t.ticket_id ASC
            LIMIT %s OFFSET %s;
        """

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                try:
                    cur.execute(select_query, params + [limit, offset])
                    rows = cur.fetchall()
                    return [_serialize_row(dict(r)) for r in rows]
                except Exception as exc:
                    logger.error(f"Search query failed on normalized tickets: {exc}")
                    conn.rollback()

        return []

    @classmethod
    def create_ticket(cls, ticket_data: dict[str, Any]) -> dict[str, Any]:
        """Insert a newly created ticket into PostgreSQL normalized and source tables."""
        schema = settings.SCHEMA or "support"

        ticket_id = ticket_data["ticket_id"]
        t_uuid = ticket_data.get("id") or str(uuid.uuid4())
        org_id = ticket_data["org_id"]
        customer_uuid = ticket_data["customer_id"]
        title = ticket_data["title"]
        subject = ticket_data.get("subject", title)
        description = ticket_data["description"]
        category = ticket_data.get("category", "general")
        priority = ticket_data.get("priority", "medium")
        status = ticket_data.get("status", "open")
        created_at = ticket_data.get("created_at") or datetime.utcnow()
        updated_at = ticket_data.get("updated_at") or created_at

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. Resolve status_id
                cur.execute(f"SELECT status_id FROM {schema}.ticket_statuses WHERE LOWER(status_name) = LOWER(%s);", (status,))
                r = cur.fetchone()
                status_id = r[0] if r else 1

                # 2. Resolve priority_id
                cur.execute(f"SELECT priority_id FROM {schema}.ticket_priorities WHERE LOWER(priority_name) = LOWER(%s);", (priority,))
                r = cur.fetchone()
                priority_id = r[0] if r else 1

                # 3. Resolve ticket_type_id
                cur.execute(f"SELECT ticket_type_id FROM {schema}.ticket_types WHERE LOWER(type_name) = LOWER(%s);", (category,))
                r = cur.fetchone()
                type_id = r[0] if r else 1

                # 4. Insert into tickets
                cur.execute(f"""
                INSERT INTO {schema}.tickets (
                    ticket_id, id, org_id, customer_uuid, ticket_type_id,
                    subject, title, description, status_id, priority_id,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    ticket_id, t_uuid, org_id, customer_uuid, type_id,
                    subject, title, description, status_id, priority_id,
                    created_at, updated_at
                ))

                # 5. Insert into source table
                cur.execute(f"""
                INSERT INTO {schema}.ticket_source_data (
                    ticket_id, id, org_id, customer_id_uuid, ticket_type,
                    ticket_subject, title, ticket_description, ticket_status,
                    ticket_priority, raw_data, imported_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    ticket_id, t_uuid, org_id, customer_uuid, category,
                    subject, title, description, status,
                    priority, psycopg2.extras.Json(ticket_data), created_at, updated_at
                ))

                conn.commit()

        return ticket_data

    @classmethod
    def update_ticket_status(cls, ticket_id: Any, new_status: str, reason: Optional[str] = None) -> bool:
        """Update ticket status and optional resolution in PostgreSQL."""
        schema = settings.SCHEMA or "support"
        is_int = False
        int_id = None
        try:
            int_id = int(ticket_id)
            is_int = True
        except (ValueError, TypeError):
            pass
        str_id = str(ticket_id).strip()

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT status_id FROM {schema}.ticket_statuses WHERE LOWER(status_name) = LOWER(%s);", (new_status.strip(),))
                row = cur.fetchone()
                if row:
                    status_id = row[0]
                else:
                    cur.execute(
                        f"INSERT INTO {schema}.ticket_statuses (status_name) VALUES (%s) RETURNING status_id;",
                        (new_status.capitalize(),)
                    )
                    status_id = cur.fetchone()[0]

                where_sql = "(ticket_id = %s OR id::text = %s)"
                params = (int_id if is_int else -1, str_id)

                if reason and new_status.strip().lower() in ("resolved", "closed"):
                    cur.execute(f"""
                    UPDATE {schema}.tickets
                    SET status_id = %s,
                        resolution = COALESCE(resolution, %s),
                        resolved_at = COALESCE(resolved_at, NOW()),
                        updated_at = NOW()
                    WHERE {where_sql};
                    """, (status_id, reason) + params)

                    cur.execute(f"""
                    UPDATE {schema}.ticket_source_data
                    SET ticket_status = %s,
                        resolution = COALESCE(resolution, %s),
                        time_to_resolution = COALESCE(time_to_resolution, NOW()),
                        updated_at = NOW()
                    WHERE {where_sql};
                    """, (new_status.capitalize(), reason) + params)
                else:
                    cur.execute(f"""
                    UPDATE {schema}.tickets
                    SET status_id = %s,
                        updated_at = NOW()
                    WHERE {where_sql};
                    """, (status_id,) + params)

                    cur.execute(f"""
                    UPDATE {schema}.ticket_source_data
                    SET ticket_status = %s,
                        updated_at = NOW()
                    WHERE {where_sql};
                    """, (new_status.capitalize(),) + params)

                conn.commit()
                return cur.rowcount > 0

    @classmethod
    def add_internal_note(cls, note_record: dict[str, Any]) -> bool:
        """Store an internal staff note in PostgreSQL."""
        schema = settings.SCHEMA or "support"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Ensure ticket_id column is TEXT
                cur.execute(f"ALTER TABLE {schema}.ticket_internal_notes ALTER COLUMN ticket_id TYPE TEXT;")
                cur.execute(f"""
                INSERT INTO {schema}.ticket_internal_notes (
                    id, note_id, ticket_id, org_id, author_id, author, note, is_private, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    note_record["id"],
                    note_record["id"],
                    str(note_record["ticket_id"]),
                    note_record["org_id"],
                    note_record["author_id"],
                    note_record.get("author_id"),
                    note_record["note"],
                    True,
                    note_record.get("created_at") or datetime.utcnow(),
                ))
                conn.commit()
                return True

    @classmethod
    def get_invoice(cls, invoice_id: str) -> Optional[dict[str, Any]]:
        """Retrieve invoice details from PostgreSQL."""
        schema = settings.SCHEMA or "support"
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"SELECT * FROM {schema}.invoices WHERE invoice_id = %s LIMIT 1;", (invoice_id.strip(),))
                row = cur.fetchone()
                if row:
                    return _serialize_row(dict(row))
        return None

    @classmethod
    def record_refund(cls, refund_record: dict[str, Any], new_invoice_status: str, new_refunded_total: float) -> bool:
        """Atomically record refund audit log and update invoice status/balance."""
        schema = settings.SCHEMA or "support"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                INSERT INTO {schema}.ticket_refunds (
                    refund_id, invoice_id, org_id, amount, reason, idempotency_key, authorized_by, processed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    refund_record["refund_id"],
                    refund_record["invoice_id"],
                    refund_record["org_id"],
                    refund_record["amount"],
                    refund_record["reason"],
                    refund_record["idempotency_key"],
                    refund_record["authorized_by"],
                    refund_record.get("processed_at") or datetime.utcnow(),
                ))

                cur.execute(f"""
                UPDATE {schema}.invoices
                SET refunded_amount = %s,
                    status = %s,
                    updated_at = NOW()
                WHERE invoice_id = %s;
                """, (new_refunded_total, new_invoice_status, refund_record["invoice_id"]))

                conn.commit()
                return True

    @classmethod
    def get_refund_by_idempotency_key(cls, idempotency_key: str) -> Optional[dict[str, Any]]:
        """Look up past refund by idempotency key."""
        schema = settings.SCHEMA or "support"
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"""
                SELECT r.*, i.total_amount, i.status AS invoice_status, i.refunded_amount
                FROM {schema}.ticket_refunds r
                JOIN {schema}.invoices i ON r.invoice_id = i.invoice_id
                WHERE r.idempotency_key = %s LIMIT 1;
                """, (idempotency_key.strip(),))
                row = cur.fetchone()
                if row:
                    data = _serialize_row(dict(row))
                    return {
                        "invoice_id": data["invoice_id"],
                        "id": data["invoice_id"],
                        "org_id": data["org_id"],
                        "total_amount": data["total_amount"],
                        "refunded_amount": data["refunded_amount"],
                        "status": data["invoice_status"],
                        "refund_details": data,
                    }
        return None

    @classmethod
    def get_max_ticket_id(cls) -> int:
        """Return the highest current ticket_id integer in PostgreSQL."""
        schema = settings.SCHEMA or "support"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COALESCE(MAX(ticket_id), 100) FROM {schema}.tickets;")
                return cur.fetchone()[0]

    @classmethod
    def customer_exists_in_org(cls, customer_uuid: str, org_id: str) -> bool:
        """Verify whether customer_uuid belongs to tenant org in PostgreSQL."""
        schema = settings.SCHEMA or "support"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                SELECT 1 FROM {schema}.customers 
                WHERE (customer_uuid = %s OR customer_id::text = %s) AND org_id = %s
                LIMIT 1;
                """, (customer_uuid.strip(), customer_uuid.strip(), org_id.strip()))
                return cur.fetchone() is not None

    @classmethod
    def is_approval_token_consumed(cls, token_hash: str) -> bool:
        """Check whether an approval token hash has already been consumed in PostgreSQL."""
        schema = settings.SCHEMA or "support"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {schema}.consumed_approval_tokens (
                    token_hash TEXT PRIMARY KEY,
                    invoice_id TEXT NOT NULL,
                    org_id UUID NOT NULL,
                    consumed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """)
                cur.execute(
                    f"SELECT 1 FROM {schema}.consumed_approval_tokens WHERE token_hash = %s LIMIT 1;",
                    (token_hash,),
                )
                return cur.fetchone() is not None

    @classmethod
    def mark_approval_token_consumed(cls, token_hash: str, invoice_id: str, org_id: str) -> None:
        """Persist consumed approval token hash in PostgreSQL to prevent replay across restarts."""
        schema = settings.SCHEMA or "support"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {schema}.consumed_approval_tokens (
                    token_hash TEXT PRIMARY KEY,
                    invoice_id TEXT NOT NULL,
                    org_id UUID NOT NULL,
                    consumed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """)
                cur.execute(f"""
                INSERT INTO {schema}.consumed_approval_tokens (token_hash, invoice_id, org_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (token_hash) DO NOTHING;
                """, (token_hash, str(invoice_id), str(org_id)))
                conn.commit()
