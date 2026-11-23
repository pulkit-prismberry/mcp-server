"""Standardized API response formatting helpers conforming to Team Contract v2.0."""
from typing import Any, Optional


def success_response(data: Any) -> dict[str, Any]:
    """Create a standardized successful response."""
    return {
        "success": True,
        "data": data,
        "error": None,
    }


def error_response(code: str, message: str, details: Optional[Any] = None) -> dict[str, Any]:
    """Create a standardized error response conforming to Contract Section 3.

    Args:
        code: One of UNAUTHORIZED, FORBIDDEN, NOT_FOUND, VALIDATION_ERROR, CONFLICT, INTERNAL_ERROR.
        message: Human-readable error description.
        details: Optional additional diagnostic details.

    Returns:
        Dictionary with standard error envelope.
    """
    return {
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }
