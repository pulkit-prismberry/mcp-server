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

    # MCP-2.1: Auth Context Propagation & /verify-token settings
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    AUTH_VERIFY_URL: str = os.getenv("AUTH_VERIFY_URL", "")
    VERIFY_TOKEN_MODE: str = os.getenv("VERIFY_TOKEN_MODE", "auto").lower()
    VERIFY_TOKEN_TIMEOUT: float = float(os.getenv("VERIFY_TOKEN_TIMEOUT", "5.0"))
    REQUIRE_AUTH_CONTEXT: bool = os.getenv("REQUIRE_AUTH_CONTEXT", "false").lower() in ("true", "1", "yes")


settings = Settings()
