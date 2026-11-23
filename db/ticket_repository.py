"""Repository for executing PostgreSQL queries on support ticket tables."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
import psycopg2.extras

from config import settings
from db.connection import get_db_connection


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert PostgreSQL dates, datetimes, and decimals to JSON-friendly types."""
    serialized = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            serialized[k] = v.isoformat()
        elif isinstance(v, Decimal):
            serialized[k] = float(v)
        else:
            serialized[k] = v
    return serialized


class TicketRepository:
    """Database repository for querying and updating support tickets in PostgreSQL."""

    @classmethod
    def get_by_id(cls, ticket_id: int) -> Optional[dict[str, Any]]:
        """Fetch ticket details from PostgreSQL by ticket_id.

        Checks normalized `support.tickets` joined with dimension tables,
        and falls back to `support.ticket_source_data` if needed.

        Args:
            ticket_id: Positive integer ticket ID.

        Returns:
            Dictionary with ticket fields, or None if not found.
        """
        schema = settings.SCHEMA

        normalized_query = f"""
            SELECT 
                t.ticket_id,
                t.subject,
                t.description,
                s.status_name AS status,
                p.priority_name AS priority,
                c.customer_id,
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
            LEFT JOIN {schema}.customers c ON t.customer_id = c.customer_id
            LEFT JOIN {schema}.products prod ON t.product_id = prod.product_id
            LEFT JOIN {schema}.ticket_types tt ON t.ticket_type_id = tt.ticket_type_id
            LEFT JOIN {schema}.ticket_statuses s ON t.status_id = s.status_id
            LEFT JOIN {schema}.ticket_priorities p ON t.priority_id = p.priority_id
            LEFT JOIN {schema}.ticket_channels ch ON t.channel_id = ch.channel_id
            WHERE t.ticket_id = %s;
        """

        source_query = f"""
            SELECT 
                ticket_id,
                ticket_subject AS subject,
                ticket_description AS description,
                ticket_status AS status,
                ticket_priority AS priority,
                customer_name,
                customer_email,
                customer_age,
                customer_gender,
                product_purchased,
                date_of_purchase AS purchase_date,
                ticket_type,
                ticket_channel,
                resolution,
                first_response_time AS first_response_at,
                time_to_resolution AS resolved_at,
                customer_satisfaction_rating AS satisfaction_rating,
                imported_at AS created_at,
                updated_at
            FROM {schema}.ticket_source_data
            WHERE ticket_id = %s;
        """

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                try:
                    cur.execute(normalized_query, (ticket_id,))
                    row = cur.fetchone()
                    if row:
                        return _serialize_row(dict(row))
                except Exception:
                    conn.rollback()

                try:
                    cur.execute(source_query, (ticket_id,))
                    row = cur.fetchone()
                    if row:
                        return _serialize_row(dict(row))
                except Exception:
                    conn.rollback()

        return None

    @classmethod
    def search(
        cls,
        query: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        customer_email: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Search and filter tickets from PostgreSQL.

        Args:
            query: Keyword matched against subject and description (ILIKE).
            status: Exact match on ticket status name (case-insensitive).
            priority: Exact match on ticket priority name (case-insensitive).
            customer_email: Exact match on customer email (case-insensitive).
            limit: Maximum records to return.
            offset: Number of records to skip.

        Returns:
            Tuple of (list_of_ticket_dicts, total_matching_count).
        """
        schema = settings.SCHEMA

        where_clauses = []
        params: list[Any] = []

        if query:
            where_clauses.append("(t.subject ILIKE %s OR t.description ILIKE %s)")
            params.extend([f"%{query}%", f"%{query}%"])
        if status:
            where_clauses.append("LOWER(s.status_name) = LOWER(%s)")
            params.append(status.strip())
        if priority:
            where_clauses.append("LOWER(p.priority_name) = LOWER(%s)")
            params.append(priority.strip())
        if customer_email:
            where_clauses.append("LOWER(c.email) = LOWER(%s)")
            params.append(customer_email.strip())

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        from_sql = f"""
            FROM {schema}.tickets t
            LEFT JOIN {schema}.customers c ON t.customer_id = c.customer_id
            LEFT JOIN {schema}.products prod ON t.product_id = prod.product_id
            LEFT JOIN {schema}.ticket_types tt ON t.ticket_type_id = tt.ticket_type_id
            LEFT JOIN {schema}.ticket_statuses s ON t.status_id = s.status_id
            LEFT JOIN {schema}.ticket_priorities p ON t.priority_id = p.priority_id
            LEFT JOIN {schema}.ticket_channels ch ON t.channel_id = ch.channel_id
        """

        count_query = f"SELECT COUNT(*) {from_sql} {where_sql};"
        select_query = f"""
            SELECT 
                t.ticket_id,
                t.subject,
                t.description,
                s.status_name AS status,
                p.priority_name AS priority,
                c.customer_id,
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
            {from_sql}
            {where_sql}
            ORDER BY t.ticket_id ASC
            LIMIT %s OFFSET %s;
        """

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                try:
                    cur.execute(count_query, params)
                    total_count = cur.fetchone()["count"]

                    cur.execute(select_query, params + [limit, offset])
                    rows = cur.fetchall()
                    return [_serialize_row(dict(r)) for r in rows], total_count
                except Exception:
                    conn.rollback()

                src_where = []
                src_params: list[Any] = []
                if query:
                    src_where.append("(ticket_subject ILIKE %s OR ticket_description ILIKE %s)")
                    src_params.extend([f"%{query}%", f"%{query}%"])
                if status:
                    src_where.append("LOWER(ticket_status) = LOWER(%s)")
                    src_params.append(status.strip())
                if priority:
                    src_where.append("LOWER(ticket_priority) = LOWER(%s)")
                    src_params.append(priority.strip())
                if customer_email:
                    src_where.append("LOWER(customer_email) = LOWER(%s)")
                    src_params.append(customer_email.strip())

                src_where_sql = f"WHERE {' AND '.join(src_where)}" if src_where else ""
                src_count_q = f"SELECT COUNT(*) FROM {schema}.ticket_source_data {src_where_sql};"
                src_select_q = f"""
                    SELECT 
                        ticket_id,
                        ticket_subject AS subject,
                        ticket_description AS description,
                        ticket_status AS status,
                        ticket_priority AS priority,
                        customer_name,
                        customer_email,
                        customer_age,
                        customer_gender,
                        product_purchased,
                        date_of_purchase AS purchase_date,
                        ticket_type,
                        ticket_channel,
                        resolution,
                        first_response_time AS first_response_at,
                        time_to_resolution AS resolved_at,
                        customer_satisfaction_rating AS satisfaction_rating,
                        imported_at AS created_at,
                        updated_at
                    FROM {schema}.ticket_source_data
                    {src_where_sql}
                    ORDER BY ticket_id ASC
                    LIMIT %s OFFSET %s;
                """

                try:
                    cur.execute(src_count_q, src_params)
                    total_count = cur.fetchone()["count"]

                    cur.execute(src_select_q, src_params + [limit, offset])
                    rows = cur.fetchall()
                    return [_serialize_row(dict(r)) for r in rows], total_count
                except Exception:
                    conn.rollback()

        return [], 0

    @classmethod
    def update_ticket_status(
        cls,
        ticket_id: int,
        new_status: str,
        reason: Optional[str] = None,
    ) -> bool:
        """Update ticket status in PostgreSQL.

        Updates both `support.tickets` (via `status_id`) and `support.ticket_source_data`.

        Args:
            ticket_id: Positive integer ticket ID.
            new_status: Target status string (e.g. 'open', 'processing', 'resolved', 'closed').
            reason: Optional justification or resolution text.

        Returns:
            True if at least one row was updated in the database; False otherwise.
        """
        schema = settings.SCHEMA
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. Lookup or insert status_id in ticket_statuses
                cur.execute(
                    f"SELECT status_id FROM {schema}.ticket_statuses WHERE LOWER(status_name) = LOWER(%s);",
                    (new_status.strip(),)
                )
                row = cur.fetchone()
                if row:
                    status_id = row[0]
                else:
                    cur.execute(
                        f"""INSERT INTO {schema}.ticket_statuses (status_name)
                        VALUES (%s)
                        ON CONFLICT (status_name) DO UPDATE SET status_name = EXCLUDED.status_name
                        RETURNING status_id;""",
                        (new_status.strip().capitalize(),)
                    )
                    status_id = cur.fetchone()[0]

                # 2. Update normalized tickets table
                tickets_updated = 0
                try:
                    if reason and new_status.strip().lower() in ("resolved", "closed"):
                        cur.execute(
                            f"""UPDATE {schema}.tickets
                            SET status_id = %s,
                                resolution = COALESCE(resolution, %s),
                                resolved_at = COALESCE(resolved_at, NOW()),
                                updated_at = NOW()
                            WHERE ticket_id = %s;""",
                            (status_id, reason, ticket_id)
                        )
                    else:
                        cur.execute(
                            f"""UPDATE {schema}.tickets
                            SET status_id = %s,
                                updated_at = NOW()
                            WHERE ticket_id = %s;""",
                            (status_id, ticket_id)
                        )
                    tickets_updated = cur.rowcount
                except Exception:
                    conn.rollback()

                # 3. Update source data table
                source_updated = 0
                try:
                    if reason and new_status.strip().lower() in ("resolved", "closed"):
                        cur.execute(
                            f"""UPDATE {schema}.ticket_source_data
                            SET ticket_status = %s,
                                resolution = COALESCE(resolution, %s),
                                time_to_resolution = COALESCE(time_to_resolution, NOW()),
                                updated_at = NOW()
                            WHERE ticket_id = %s;""",
                            (new_status.strip().capitalize(), reason, ticket_id)
                        )
                    else:
                        cur.execute(
                            f"""UPDATE {schema}.ticket_source_data
                            SET ticket_status = %s,
                                updated_at = NOW()
                            WHERE ticket_id = %s;""",
                            (new_status.strip().capitalize(), ticket_id)
                        )
                    source_updated = cur.rowcount
                except Exception:
                    conn.rollback()

                conn.commit()
                return (tickets_updated > 0 or source_updated > 0)

    @classmethod
    def add_internal_note(
        cls,
        ticket_id: int,
        note_id: str,
        note: str,
        author: str = "support_agent_ai",
        is_private: bool = True,
    ) -> bool:
        """Store an internal note in PostgreSQL."""
        schema = settings.SCHEMA
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        f"""CREATE TABLE IF NOT EXISTS {schema}.ticket_internal_notes (
                            note_id TEXT PRIMARY KEY,
                            ticket_id BIGINT NOT NULL,
                            note TEXT NOT NULL,
                            author TEXT NOT NULL,
                            is_private BOOLEAN NOT NULL DEFAULT TRUE,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );"""
                    )
                    cur.execute(
                        f"""INSERT INTO {schema}.ticket_internal_notes (note_id, ticket_id, note, author, is_private, created_at)
                        VALUES (%s, %s, %s, %s, %s, NOW());""",
                        (note_id, ticket_id, note, author, is_private)
                    )
                    conn.commit()
                    return True
                except Exception:
                    conn.rollback()
                    return False

    @classmethod
    def issue_refund(
        cls,
        ticket_id: int,
        refund_id: str,
        amount: float,
        reason: str,
        currency: str = "USD",
        agent_id: Optional[str] = "support_agent_ai",
    ) -> bool:
        """Store a refund record in PostgreSQL."""
        schema = settings.SCHEMA
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        f"""CREATE TABLE IF NOT EXISTS {schema}.ticket_refunds (
                            refund_id TEXT PRIMARY KEY,
                            ticket_id BIGINT NOT NULL,
                            amount NUMERIC(10, 2) NOT NULL,
                            currency VARCHAR(3) NOT NULL DEFAULT 'USD',
                            status TEXT NOT NULL DEFAULT 'processed',
                            reason TEXT NOT NULL,
                            agent_id TEXT,
                            processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );"""
                    )
                    cur.execute(
                        f"""INSERT INTO {schema}.ticket_refunds (refund_id, ticket_id, amount, currency, status, reason, agent_id, processed_at)
                        VALUES (%s, %s, %s, %s, 'processed', %s, %s, NOW());""",
                        (refund_id, ticket_id, amount, currency, reason, agent_id)
                    )
                    conn.commit()
                    return True
                except Exception:
                    conn.rollback()
                    return False
