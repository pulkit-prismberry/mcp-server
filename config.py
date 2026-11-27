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

    # Contract v3.0 Section 2.C: User Context Resolution (GET /auth/me)
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    AUTH_ME_URL: str = os.getenv("AUTH_ME_URL", "")
    AUTH_VERIFY_URL: str = os.getenv("AUTH_VERIFY_URL", "")
    VERIFY_TOKEN_MODE: str = os.getenv("VERIFY_TOKEN_MODE", "auto").lower()
    VERIFY_TOKEN_TIMEOUT: float = float(os.getenv("VERIFY_TOKEN_TIMEOUT", "5.0"))
    REQUIRE_AUTH_CONTEXT: bool = os.getenv("REQUIRE_AUTH_CONTEXT", "true").lower() in ("true", "1", "yes")

    # JWT Settings (Contract v3.0 Section 2.A & 2.B)
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-secret-key-support-ai-2026-super-secure-key-32bytes")
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = os.getenv("JWT_ISSUER", "support-ai-backend")
    JWT_AUDIENCE: str = os.getenv("JWT_AUDIENCE", "support-ai-services")


settings = Settings()
