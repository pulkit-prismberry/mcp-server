"""PostgreSQL database connection management."""
from contextlib import contextmanager
from typing import Generator
import psycopg2
from psycopg2.extensions import connection as PgConnection

from config import settings


def get_connection_params() -> dict[str, str]:
    """Retrieve connection dictionary for psycopg2."""
    if settings.DATABASE_URL:
        return {"dsn": settings.DATABASE_URL}

    params = {
        "host": settings.PGHOST,
        "port": settings.PGPORT,
        "dbname": settings.PGDATABASE,
        "user": settings.PGUSER,
        "sslmode": settings.PGSSLMODE,
    }
    if settings.PGPASSWORD:
        params["password"] = settings.PGPASSWORD
    return params


@contextmanager
def get_db_connection() -> Generator[PgConnection, None, None]:
    """Context manager for obtaining a database connection with auto-closing."""
    params = get_connection_params()
    conn = psycopg2.connect(**params)
    try:
        yield conn
    finally:
        conn.close()


def is_db_connected() -> bool:
    """Check if PostgreSQL database is reachable."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                return True
    except Exception:
        return False
