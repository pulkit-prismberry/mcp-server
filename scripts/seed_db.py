#!/usr/bin/env python3
"""Script to wipe all records from PostgreSQL and insert exactly the 4 hardcoded records.

Contract v3.0 Locked:
- 4 Tickets: 101, 102, 201, 202
- Multi-tenant organizations: Org A and Org B
- Invoices: inv_org_a_001 and inv_org_b_001
- Verified customers: Charlie, Second Customer Org A, Customer Org B, Alice, Bob, Dave
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg2
from psycopg2.extras import RealDictCursor
from config import settings
from db.connection import get_db_connection
from utils.auth import ALICE_CONTEXT, BOB_CONTEXT, CHARLIE_CONTEXT, DAVE_CONTEXT

SCHEMA = settings.SCHEMA or "support"
ORG_A_ID = ALICE_CONTEXT["org_id"]
ORG_B_ID = DAVE_CONTEXT["org_id"]
CHARLIE_CUST_ID = CHARLIE_CONTEXT["customer_id"]


def reset_and_seed():
    print(f"Connecting to database '{settings.PGDATABASE}' on {settings.PGHOST}:{settings.PGPORT}...")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # 1. Create schema if needed
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA};")

            # 2. Ensure tables & extra columns exist
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA}.ticket_statuses (
                status_id SMALLSERIAL PRIMARY KEY,
                status_name TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS {SCHEMA}.ticket_priorities (
                priority_id SMALLSERIAL PRIMARY KEY,
                priority_name TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS {SCHEMA}.ticket_types (
                ticket_type_id SMALLSERIAL PRIMARY KEY,
                type_name TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS {SCHEMA}.ticket_channels (
                channel_id SMALLSERIAL PRIMARY KEY,
                channel_name TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS {SCHEMA}.products (
                product_id BIGSERIAL PRIMARY KEY,
                product_name TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS {SCHEMA}.customers (
                customer_id BIGSERIAL PRIMARY KEY,
                customer_uuid TEXT,
                org_id UUID,
                full_name TEXT,
                email TEXT,
                age SMALLINT,
                gender TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS {SCHEMA}.tickets (
                ticket_id BIGINT PRIMARY KEY,
                id UUID,
                org_id UUID,
                customer_id BIGINT,
                customer_uuid TEXT,
                product_id BIGINT,
                purchase_date DATE,
                ticket_type_id SMALLINT,
                subject TEXT,
                title TEXT,
                description TEXT,
                status_id SMALLINT,
                resolution TEXT,
                priority_id SMALLINT,
                channel_id SMALLINT,
                invoice_id TEXT,
                first_response_at TIMESTAMPTZ,
                resolved_at TIMESTAMPTZ,
                satisfaction_rating NUMERIC,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS {SCHEMA}.ticket_source_data (
                ticket_id BIGINT PRIMARY KEY,
                id UUID,
                org_id UUID,
                customer_name TEXT,
                customer_email TEXT,
                customer_id_uuid TEXT,
                customer_age INTEGER,
                customer_gender TEXT,
                product_purchased TEXT,
                date_of_purchase DATE,
                ticket_type TEXT,
                ticket_subject TEXT,
                title TEXT,
                ticket_description TEXT,
                ticket_status TEXT,
                resolution TEXT,
                ticket_priority TEXT,
                ticket_channel TEXT,
                invoice_id TEXT,
                first_response_time TIMESTAMPTZ,
                time_to_resolution TIMESTAMPTZ,
                customer_satisfaction_rating NUMERIC,
                raw_data JSONB,
                imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS {SCHEMA}.invoices (
                invoice_id TEXT PRIMARY KEY,
                id TEXT,
                org_id UUID NOT NULL,
                customer_id TEXT NOT NULL,
                total_amount NUMERIC(10, 2) NOT NULL,
                refunded_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
                status TEXT NOT NULL DEFAULT 'paid',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS {SCHEMA}.ticket_internal_notes (
                id TEXT PRIMARY KEY,
                note_id TEXT,
                ticket_id TEXT NOT NULL,
                org_id UUID,
                author_id TEXT,
                note TEXT NOT NULL,
                is_private BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS {SCHEMA}.ticket_refunds (
                refund_id TEXT PRIMARY KEY,
                invoice_id TEXT NOT NULL,
                org_id UUID NOT NULL,
                amount NUMERIC(10, 2) NOT NULL,
                reason TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                authorized_by TEXT NOT NULL,
                processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """)

            # Add any missing columns to existing tables
            alter_queries = [
                f"ALTER TABLE {SCHEMA}.tickets ADD COLUMN IF NOT EXISTS id UUID;",
                f"ALTER TABLE {SCHEMA}.tickets ADD COLUMN IF NOT EXISTS org_id UUID;",
                f"ALTER TABLE {SCHEMA}.tickets ADD COLUMN IF NOT EXISTS customer_uuid TEXT;",
                f"ALTER TABLE {SCHEMA}.tickets ADD COLUMN IF NOT EXISTS invoice_id TEXT;",
                f"ALTER TABLE {SCHEMA}.tickets ADD COLUMN IF NOT EXISTS title TEXT;",
                f"ALTER TABLE {SCHEMA}.ticket_source_data ADD COLUMN IF NOT EXISTS id UUID;",
                f"ALTER TABLE {SCHEMA}.ticket_source_data ADD COLUMN IF NOT EXISTS org_id UUID;",
                f"ALTER TABLE {SCHEMA}.ticket_source_data ADD COLUMN IF NOT EXISTS customer_id_uuid TEXT;",
                f"ALTER TABLE {SCHEMA}.ticket_source_data ADD COLUMN IF NOT EXISTS invoice_id TEXT;",
                f"ALTER TABLE {SCHEMA}.ticket_source_data ADD COLUMN IF NOT EXISTS title TEXT;",
                f"ALTER TABLE {SCHEMA}.customers ADD COLUMN IF NOT EXISTS customer_uuid TEXT;",
                f"ALTER TABLE {SCHEMA}.customers ADD COLUMN IF NOT EXISTS org_id UUID;",
                f"ALTER TABLE {SCHEMA}.ticket_internal_notes ADD COLUMN IF NOT EXISTS id TEXT;",
                f"ALTER TABLE {SCHEMA}.ticket_internal_notes ADD COLUMN IF NOT EXISTS org_id UUID;",
                f"ALTER TABLE {SCHEMA}.ticket_internal_notes ADD COLUMN IF NOT EXISTS author_id TEXT;",
                f"ALTER TABLE {SCHEMA}.ticket_internal_notes ALTER COLUMN author DROP NOT NULL;",
            ]
            for q in alter_queries:
                cur.execute(q)

            # 3. WIPE EVERY RECORD FROM ALL TABLES
            print("Wiping all existing records from PostgreSQL...")
            tables_to_truncate = [
                "tickets",
                "ticket_source_data",
                "customers",
                "invoices",
                "ticket_internal_notes",
                "ticket_refunds",
            ]
            for tbl in tables_to_truncate:
                cur.execute(f"TRUNCATE TABLE {SCHEMA}.{tbl} CASCADE;")
            print("All existing records removed.")

            # 4. Seed Dimension Values
            statuses = ["Open", "In_progress", "Resolved", "Closed"]
            for s in statuses:
                cur.execute(
                    f"INSERT INTO {SCHEMA}.ticket_statuses (status_name) VALUES (%s) ON CONFLICT (status_name) DO NOTHING;",
                    (s,)
                )

            priorities = ["Low", "Medium", "High", "Urgent"]
            for p in priorities:
                cur.execute(
                    f"INSERT INTO {SCHEMA}.ticket_priorities (priority_name) VALUES (%s) ON CONFLICT (priority_name) DO NOTHING;",
                    (p,)
                )

            types = ["Billing", "Technical", "Account", "General"]
            for t in types:
                cur.execute(
                    f"INSERT INTO {SCHEMA}.ticket_types (type_name) VALUES (%s) ON CONFLICT (type_name) DO NOTHING;",
                    (t,)
                )

            channels = ["web", "email", "chat", "phone"]
            for ch in channels:
                cur.execute(
                    f"INSERT INTO {SCHEMA}.ticket_channels (channel_name) VALUES (%s) ON CONFLICT (channel_name) DO NOTHING;",
                    (ch,)
                )

            cur.execute(
                f"INSERT INTO {SCHEMA}.products (product_name) VALUES ('SaaS Platform Enterprise'), ('Custom Domain Service') ON CONFLICT DO NOTHING;"
            )

            # Map helper functions for dimension IDs
            col_id_map = {
                "ticket_statuses": "status_id",
                "ticket_priorities": "priority_id",
                "ticket_types": "ticket_type_id",
                "ticket_channels": "channel_id",
                "products": "product_id",
            }

            def get_dim_id(table, col, val):
                id_col = col_id_map.get(table, "id")
                cur.execute(f"SELECT {id_col} FROM {SCHEMA}.{table} WHERE LOWER({col}) = LOWER(%s);", (val.strip(),))
                row = cur.fetchone()
                return row[0] if row else 1

            # 5. Insert Customers (Charlie, Second Org A, Customer Org B, Alice, Bob, Dave)
            customers_data = [
                (1, CHARLIE_CUST_ID, ORG_A_ID, "Charlie Customer", "charlie@customer.com", 30, "Female"),
                (2, "other_cust_2222-2222-2222-222222222222", ORG_A_ID, "Second Customer Org A", "second@orga.com", 35, "Male"),
                (3, "cust_b_3333-3333-3333-333333333333", ORG_B_ID, "Customer Org B", "custb@orgb.com", 28, "Non-binary"),
                (4, ALICE_CONTEXT["user_id"], ORG_A_ID, "Alice Admin", "alice@orga.com", 40, "Female"),
                (5, BOB_CONTEXT["user_id"], ORG_A_ID, "Bob Support", "bob@orga.com", 32, "Male"),
                (6, DAVE_CONTEXT["user_id"], ORG_B_ID, "Dave Admin", "dave@orgb.com", 38, "Male"),
            ]
            for cid, cuuid, oid, name, email, age, gender in customers_data:
                cur.execute(f"""
                INSERT INTO {SCHEMA}.customers (customer_id, customer_uuid, org_id, full_name, email, age, gender)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, (cid, cuuid, oid, name, email, age, gender))

            # 6. Insert EXACTLY 4 TICKET RECORDS
            four_tickets = [
                {
                    "ticket_id": 101,
                    "id": "10111111-1111-1111-1111-111111111111",
                    "org_id": ORG_A_ID,
                    "customer_id": 1,
                    "customer_uuid": CHARLIE_CUST_ID,
                    "customer_name": "Charlie Customer",
                    "customer_email": "charlie@customer.com",
                    "customer_age": 30,
                    "customer_gender": "Female",
                    "product_name": "SaaS Platform Enterprise",
                    "subject": "Subscription renewal overcharge",
                    "title": "Subscription renewal overcharge",
                    "description": "Customer was overcharged on annual renewal.",
                    "status": "open",
                    "priority": "high",
                    "category": "billing",
                    "channel": "web",
                    "invoice_id": "inv_org_a_001",
                    "resolution": None,
                    "created_at": "2026-11-20T10:00:00Z",
                    "updated_at": "2026-11-20T10:00:00Z",
                },
                {
                    "ticket_id": 102,
                    "id": "10222222-2222-2222-2222-222222222222",
                    "org_id": ORG_A_ID,
                    "customer_id": 2,
                    "customer_uuid": "other_cust_2222-2222-2222-2222-222222222222",
                    "customer_name": "Second Customer Org A",
                    "customer_email": "second@orga.com",
                    "customer_age": 35,
                    "customer_gender": "Male",
                    "product_name": "SaaS Platform Enterprise",
                    "subject": "SSO authentication failure",
                    "title": "SSO authentication failure",
                    "description": "Internal identity provider SAML failure.",
                    "status": "in_progress",
                    "priority": "urgent",
                    "category": "technical",
                    "channel": "email",
                    "invoice_id": None,
                    "resolution": None,
                    "created_at": "2026-11-21T09:00:00Z",
                    "updated_at": "2026-11-21T11:00:00Z",
                },
                {
                    "ticket_id": 201,
                    "id": "20111111-1111-1111-1111-111111111111",
                    "org_id": ORG_B_ID,
                    "customer_id": 3,
                    "customer_uuid": "cust_b_3333-3333-3333-333333333333",
                    "customer_name": "Customer Org B",
                    "customer_email": "custb@orgb.com",
                    "customer_age": 28,
                    "customer_gender": "Non-binary",
                    "product_name": "Custom Domain Service",
                    "subject": "Org B Custom Domain TLS setup",
                    "title": "Org B Custom Domain TLS setup",
                    "description": "Requesting TLS cert configuration for custom domain.",
                    "status": "open",
                    "priority": "medium",
                    "category": "account",
                    "channel": "chat",
                    "invoice_id": "inv_org_b_001",
                    "resolution": None,
                    "created_at": "2026-11-22T08:00:00Z",
                    "updated_at": "2026-11-22T08:00:00Z",
                },
                {
                    "ticket_id": 202,
                    "id": "20222222-2222-2222-2222-222222222222",
                    "org_id": ORG_B_ID,
                    "customer_id": 3,
                    "customer_uuid": "cust_b_3333-3333-3333-333333333333",
                    "customer_name": "Customer Org B",
                    "customer_email": "custb@orgb.com",
                    "customer_age": 28,
                    "customer_gender": "Non-binary",
                    "product_name": "SaaS Platform Enterprise",
                    "subject": "Org B API Rate Limit Increase",
                    "title": "Org B API Rate Limit Increase",
                    "description": "Requesting API rate limit increase for production migration.",
                    "status": "resolved",
                    "priority": "high",
                    "category": "technical",
                    "channel": "web",
                    "invoice_id": None,
                    "resolution": "Limit increased to 5,000 req/min.",
                    "created_at": "2026-11-22T09:00:00Z",
                    "updated_at": "2026-11-22T10:00:00Z",
                },
            ]

            print(f"Inserting exactly {len(four_tickets)} ticket records into normalized & source tables...")
            for t in four_tickets:
                status_id = get_dim_id("ticket_statuses", "status_name", t["status"])
                priority_id = get_dim_id("ticket_priorities", "priority_name", t["priority"])
                type_id = get_dim_id("ticket_types", "type_name", t["category"])
                channel_id = get_dim_id("ticket_channels", "channel_name", t["channel"])
                prod_id = get_dim_id("products", "product_name", t["product_name"])

                # Insert into support.tickets
                cur.execute(f"""
                INSERT INTO {SCHEMA}.tickets (
                    ticket_id, id, org_id, customer_id, customer_uuid, product_id,
                    ticket_type_id, subject, title, description, status_id,
                    priority_id, channel_id, invoice_id, resolution,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s
                );
                """, (
                    t["ticket_id"], t["id"], t["org_id"], t["customer_id"], t["customer_uuid"], prod_id,
                    type_id, t["subject"], t["title"], t["description"], status_id,
                    priority_id, channel_id, t["invoice_id"], t["resolution"],
                    t["created_at"], t["updated_at"]
                ))

                # Insert into support.ticket_source_data
                cur.execute(f"""
                INSERT INTO {SCHEMA}.ticket_source_data (
                    ticket_id, id, org_id, customer_name, customer_email, customer_id_uuid,
                    customer_age, customer_gender, product_purchased,
                    ticket_type, ticket_subject, title, ticket_description,
                    ticket_status, resolution, ticket_priority, ticket_channel,
                    invoice_id, raw_data, imported_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                );
                """, (
                    t["ticket_id"], t["id"], t["org_id"], t["customer_name"], t["customer_email"], t["customer_uuid"],
                    t["customer_age"], t["customer_gender"], t["product_name"],
                    t["category"], t["subject"], t["title"], t["description"],
                    t["status"], t["resolution"], t["priority"], t["channel"],
                    t["invoice_id"], psycopg2.extras.Json(t), t["created_at"], t["updated_at"]
                ))

            # 7. Insert Invoices
            invoices = [
                ("inv_org_a_001", "inv_org_a_001", ORG_A_ID, CHARLIE_CUST_ID, 500.00, 0.00, "paid", "2026-11-01T12:00:00Z"),
                ("inv_org_b_001", "inv_org_b_001", ORG_B_ID, "cust_b_3333-3333-3333-333333333333", 300.00, 0.00, "paid", "2026-11-05T12:00:00Z"),
            ]
            for inv_id, i_id, oid, cid, total, refunded, status, created_at in invoices:
                cur.execute(f"""
                INSERT INTO {SCHEMA}.invoices (invoice_id, id, org_id, customer_id, total_amount, refunded_amount, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (inv_id, i_id, oid, cid, total, refunded, status, created_at, created_at))

            # 8. Insert Initial Internal Note for Ticket 101
            cur.execute(f"""
            INSERT INTO {SCHEMA}.ticket_internal_notes (id, note_id, ticket_id, org_id, author_id, author, note, is_private, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                "note_001",
                "note_001",
                "101",
                ORG_A_ID,
                BOB_CONTEXT["user_id"],
                BOB_CONTEXT["email"],
                "Verified duplicate charge. Awaiting Org_Admin approval.",
                True,
                "2026-11-20T10:15:00Z"
            ))

            conn.commit()
            print("Successfully committed hardcoded records to PostgreSQL!")


if __name__ == "__main__":
    reset_and_seed()
