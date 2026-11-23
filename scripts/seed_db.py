#!/usr/bin/env python3
"""Create PostgreSQL tables and import ALL CSV columns/rows.

Usage:
  pip install pandas psycopg2-binary
  createdb support_db
  export PGHOST=localhost PGPORT=5432 PGUSER=postgres PGPASSWORD=your_password PGDATABASE=support_db
  python scripts/seed_db.py --csv data/customer_support_tickets.csv

Creates:
  support.ticket_source_data  - full-fidelity source table (all 17 CSV columns + raw JSON)
  support.customers/products/ticket_types/ticket_statuses/ticket_priorities/ticket_channels
  support.tickets             - normalized analytics-friendly ticket table
"""
import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values, Json

SCHEMA = "support"
EXPECTED_COLUMNS = [
    "Ticket ID", "Customer Name", "Customer Email", "Customer Age",
    "Customer Gender", "Product Purchased", "Date of Purchase",
    "Ticket Type", "Ticket Subject", "Ticket Description", "Ticket Status",
    "Resolution", "Ticket Priority", "Ticket Channel", "First Response Time",
    "Time to Resolution", "Customer Satisfaction Rating",
]

DDL = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};

-- Full source data: no CSV column is discarded. raw_data preserves the original row values.
CREATE TABLE IF NOT EXISTS {SCHEMA}.ticket_source_data (
    ticket_id BIGINT PRIMARY KEY,
    customer_name TEXT,
    customer_email TEXT,
    customer_age INTEGER,
    customer_gender TEXT,
    product_purchased TEXT,
    date_of_purchase DATE,
    ticket_type TEXT,
    ticket_subject TEXT,
    ticket_description TEXT,
    ticket_status TEXT,
    resolution TEXT,
    ticket_priority TEXT,
    ticket_channel TEXT,
    first_response_time TIMESTAMP,
    time_to_resolution TIMESTAMP,
    customer_satisfaction_rating NUMERIC,
    raw_data JSONB NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS {SCHEMA}.customers (
    customer_id BIGSERIAL PRIMARY KEY,
    full_name TEXT,
    email TEXT UNIQUE,
    age SMALLINT CHECK (age IS NULL OR age BETWEEN 0 AND 120),
    gender TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS {SCHEMA}.products (
    product_id BIGSERIAL PRIMARY KEY,
    product_name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS {SCHEMA}.ticket_types (
    ticket_type_id SMALLSERIAL PRIMARY KEY,
    type_name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS {SCHEMA}.ticket_statuses (
    status_id SMALLSERIAL PRIMARY KEY,
    status_name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS {SCHEMA}.ticket_priorities (
    priority_id SMALLSERIAL PRIMARY KEY,
    priority_name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS {SCHEMA}.ticket_channels (
    channel_id SMALLSERIAL PRIMARY KEY,
    channel_name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS {SCHEMA}.tickets (
    ticket_id BIGINT PRIMARY KEY,
    customer_id BIGINT REFERENCES {SCHEMA}.customers(customer_id),
    product_id BIGINT REFERENCES {SCHEMA}.products(product_id),
    purchase_date DATE,
    ticket_type_id SMALLINT REFERENCES {SCHEMA}.ticket_types(ticket_type_id),
    subject TEXT,
    description TEXT,
    status_id SMALLINT REFERENCES {SCHEMA}.ticket_statuses(status_id),
    resolution TEXT,
    priority_id SMALLINT REFERENCES {SCHEMA}.ticket_priorities(priority_id),
    channel_id SMALLINT REFERENCES {SCHEMA}.ticket_channels(channel_id),
    first_response_at TIMESTAMP,
    resolved_at TIMESTAMP,
    satisfaction_rating NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_customer_email ON {SCHEMA}.ticket_source_data(customer_email);
CREATE INDEX IF NOT EXISTS idx_source_status ON {SCHEMA}.ticket_source_data(ticket_status);
CREATE INDEX IF NOT EXISTS idx_source_product ON {SCHEMA}.ticket_source_data(product_purchased);
CREATE INDEX IF NOT EXISTS idx_tickets_customer_id ON {SCHEMA}.tickets(customer_id);
CREATE INDEX IF NOT EXISTS idx_tickets_product_id ON {SCHEMA}.tickets(product_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status_id ON {SCHEMA}.tickets(status_id);
CREATE INDEX IF NOT EXISTS idx_tickets_priority_id ON {SCHEMA}.tickets(priority_id);
CREATE INDEX IF NOT EXISTS idx_tickets_purchase_date ON {SCHEMA}.tickets(purchase_date);
CREATE INDEX IF NOT EXISTS idx_customers_email ON {SCHEMA}.customers(email);
"""


def clean(value):
    if pd.isna(value):
        return None
    if isinstance(value, str):
        return value.strip() or None
    return value


def date_value(value):
    value = clean(value)
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def timestamp_value(value):
    value = clean(value)
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.to_pydatetime()


def seed_lookup(cur, table, column, values):
    vals = sorted({str(v).strip() for v in values if clean(v) is not None})
    if vals:
        execute_values(cur, f"INSERT INTO {SCHEMA}.{table} ({column}) VALUES %s ON CONFLICT ({column}) DO NOTHING", [(v,) for v in vals])


def resolve_csv_path(user_csv: str) -> Path:
    """Find CSV file checking path, data/ folder, and project root."""
    p = Path(user_csv)
    if p.exists():
        return p
    data_p = Path(__file__).resolve().parent.parent / "data" / user_csv
    if data_p.exists():
        return data_p
    root_p = Path(__file__).resolve().parent.parent / user_csv
    if root_p.exists():
        return root_p
    return p


def main():
    parser = argparse.ArgumentParser(description="Create PostgreSQL schema and import all CSV data.")
    parser.add_argument("--csv", default="customer_support_tickets.csv", help="CSV path")
    args = parser.parse_args()
    path = resolve_csv_path(args.csv)
    if not path.exists():
        sys.exit(f"CSV file not found: {path}")

    print(f"Running database seeding with CSV: {path}")
    df = pd.read_csv(path)
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        sys.exit("Missing required CSV columns: " + ", ".join(missing))

    records = df[EXPECTED_COLUMNS].to_dict("records")
    conn = psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "support_db"), user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
    )
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(DDL)

                source_rows = []
                for r in records:
                    source_rows.append((
                        int(r["Ticket ID"]), clean(r["Customer Name"]), clean(r["Customer Email"]),
                        clean(r["Customer Age"]), clean(r["Customer Gender"]), clean(r["Product Purchased"]),
                        date_value(r["Date of Purchase"]), clean(r["Ticket Type"]), clean(r["Ticket Subject"]),
                        clean(r["Ticket Description"]), clean(r["Ticket Status"]), clean(r["Resolution"]),
                        clean(r["Ticket Priority"]), clean(r["Ticket Channel"]),
                        timestamp_value(r["First Response Time"]), timestamp_value(r["Time to Resolution"]),
                        clean(r["Customer Satisfaction Rating"]), Json({k: (None if pd.isna(v) else v.item() if hasattr(v, 'item') else v) for k,v in r.items()}),
                    ))
                execute_values(cur, f"""INSERT INTO {SCHEMA}.ticket_source_data (
                    ticket_id, customer_name, customer_email, customer_age, customer_gender,
                    product_purchased, date_of_purchase, ticket_type, ticket_subject,
                    ticket_description, ticket_status, resolution, ticket_priority,
                    ticket_channel, first_response_time, time_to_resolution,
                    customer_satisfaction_rating, raw_data
                ) VALUES %s ON CONFLICT (ticket_id) DO UPDATE SET
                    customer_name=EXCLUDED.customer_name, customer_email=EXCLUDED.customer_email,
                    customer_age=EXCLUDED.customer_age, customer_gender=EXCLUDED.customer_gender,
                    product_purchased=EXCLUDED.product_purchased, date_of_purchase=EXCLUDED.date_of_purchase,
                    ticket_type=EXCLUDED.ticket_type, ticket_subject=EXCLUDED.ticket_subject,
                    ticket_description=EXCLUDED.ticket_description, ticket_status=EXCLUDED.ticket_status,
                    resolution=EXCLUDED.resolution, ticket_priority=EXCLUDED.ticket_priority,
                    ticket_channel=EXCLUDED.ticket_channel, first_response_time=EXCLUDED.first_response_time,
                    time_to_resolution=EXCLUDED.time_to_resolution,
                    customer_satisfaction_rating=EXCLUDED.customer_satisfaction_rating,
                    raw_data=EXCLUDED.raw_data, updated_at=NOW()""", source_rows, page_size=1000)

                # Seed dimension tables.
                for table, column, csv_col in [
                    ("ticket_types", "type_name", "Ticket Type"),
                    ("ticket_statuses", "status_name", "Ticket Status"),
                    ("ticket_priorities", "priority_name", "Ticket Priority"),
                    ("ticket_channels", "channel_name", "Ticket Channel"),
                    ("products", "product_name", "Product Purchased"),
                ]:
                    seed_lookup(cur, table, column, df[csv_col])

                # Deduplicate customer dimension records by email
                customer_by_email = {}
                for r in records:
                    email = clean(r["Customer Email"])
                    if email:
                        normalized_email = email.lower()
                        customer_by_email[normalized_email] = (
                            clean(r["Customer Name"]), normalized_email,
                            clean(r["Customer Age"]), clean(r["Customer Gender"]),
                        )
                customer_rows = list(customer_by_email.values())
                if customer_rows:
                    execute_values(cur, f"""INSERT INTO {SCHEMA}.customers (full_name,email,age,gender) VALUES %s
                    ON CONFLICT(email) DO UPDATE SET full_name=EXCLUDED.full_name, age=EXCLUDED.age,
                    gender=EXCLUDED.gender, updated_at=NOW()""", customer_rows, page_size=1000)

                cur.execute(f"SELECT email,customer_id FROM {SCHEMA}.customers")
                customers = dict(cur.fetchall())
                cur.execute(f"SELECT product_name,product_id FROM {SCHEMA}.products")
                products = dict(cur.fetchall())
                cur.execute(f"SELECT type_name,ticket_type_id FROM {SCHEMA}.ticket_types")
                types = dict(cur.fetchall())
                cur.execute(f"SELECT status_name,status_id FROM {SCHEMA}.ticket_statuses")
                statuses = dict(cur.fetchall())
                cur.execute(f"SELECT priority_name,priority_id FROM {SCHEMA}.ticket_priorities")
                priorities = dict(cur.fetchall())
                cur.execute(f"SELECT channel_name,channel_id FROM {SCHEMA}.ticket_channels")
                channels = dict(cur.fetchall())

                normalized = []
                for r in records:
                    email = clean(r["Customer Email"])
                    product = clean(r["Product Purchased"])
                    normalized.append((
                        int(r["Ticket ID"]), customers.get(email.lower()) if email else None,
                        products.get(product), date_value(r["Date of Purchase"]),
                        types.get(clean(r["Ticket Type"])), clean(r["Ticket Subject"]),
                        clean(r["Ticket Description"]), statuses.get(clean(r["Ticket Status"])),
                        clean(r["Resolution"]), priorities.get(clean(r["Ticket Priority"])),
                        channels.get(clean(r["Ticket Channel"])), timestamp_value(r["First Response Time"]),
                        timestamp_value(r["Time to Resolution"]), clean(r["Customer Satisfaction Rating"]),
                    ))
                execute_values(cur, f"""INSERT INTO {SCHEMA}.tickets (
                    ticket_id,customer_id,product_id,purchase_date,ticket_type_id,subject,description,
                    status_id,resolution,priority_id,channel_id,first_response_at,resolved_at,satisfaction_rating
                ) VALUES %s ON CONFLICT(ticket_id) DO UPDATE SET
                    customer_id=EXCLUDED.customer_id, product_id=EXCLUDED.product_id,
                    purchase_date=EXCLUDED.purchase_date, ticket_type_id=EXCLUDED.ticket_type_id,
                    subject=EXCLUDED.subject, description=EXCLUDED.description, status_id=EXCLUDED.status_id,
                    resolution=EXCLUDED.resolution, priority_id=EXCLUDED.priority_id,
                    channel_id=EXCLUDED.channel_id, first_response_at=EXCLUDED.first_response_at,
                    resolved_at=EXCLUDED.resolved_at, satisfaction_rating=EXCLUDED.satisfaction_rating,
                    updated_at=NOW()""", normalized, page_size=1000)

        print(f"Successfully imported/updated {len(df):,} rows.")
        print(f"Full CSV data table: {SCHEMA}.ticket_source_data")
        print(f"Normalized tables: {SCHEMA}.customers, products, ticket_types, ticket_statuses, ticket_priorities, ticket_channels, tickets")
        print(f"Database: {os.getenv('PGDATABASE', 'support_db')}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
