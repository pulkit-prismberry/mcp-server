"""Configuration settings for the MCP server and external integrations."""
import os
from dataclasses import dataclass
from pathlib import Path

# Load .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    SERVER_NAME: str = os.getenv("MCP_SERVER_NAME", "Multi-Tenant Support AI")
    DATA_DIR: Path = BASE_DIR / "data"
    DEFAULT_CSV_PATH: Path = DATA_DIR / "customer_support_tickets.csv"

    # PostgreSQL Database Settings
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    PGHOST: str = os.getenv("PGHOST", "localhost")
    PGPORT: str = os.getenv("PGPORT", "5432")
    PGDATABASE: str = os.getenv("PGDATABASE", "support_db")
    PGUSER: str = os.getenv("PGUSER", "postgres")
    PGPASSWORD: str = os.getenv("PGPASSWORD", "")
    PGSSLMODE: str = os.getenv("PGSSLMODE", "prefer")
    SCHEMA: str = os.getenv("PGSCHEMA", "support")

    # Fallback to mock data if PostgreSQL is unreachable (useful for dev & tests)
    USE_MOCK_FALLBACK: bool = os.getenv("USE_MOCK_FALLBACK", "true").lower() in ("true", "1", "yes")


settings = Settings()
