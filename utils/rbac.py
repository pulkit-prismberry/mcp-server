"""Tool-level RBAC & prompt-injection hardening middleware enforcing Contract v3.0 prior to DB execution."""
from functools import wraps
import inspect
import logging
from typing import Any, Callable, Optional

from utils.auth import (
    _REQUEST_VERIFIED_CTX,
    UNTRUSTED_LLM_IDENTITY_FIELDS,
    AuthVerificationError,
    extract_token_from_mcp_context,
    has_permission,
    resolve_verified_user_context,
)
from utils.responses import error_response

logger = logging.getLogger(__name__)


class PermissionDeniedError(Exception):
    """Structured exception raised when an authenticated caller lacks required permissions."""

    def __init__(
        self,
        message: str,
        required_permissions: tuple[str, ...],
        tool_name: str,
        role: Optional[str] = None,
    ):
        super().__init__(message)
        self.code = "FORBIDDEN"
        self.message = message
        self.details = {
            "error_type": "PermissionDenied",
            "tool": tool_name,
            "required_permissions": list(required_permissions),
            "role": role,
        }

    def to_response(self) -> dict[str, Any]:
        """Serialize into the Contract v3.0 error envelope."""
        return error_response(self.code, self.message, details=self.details)


def require_permissions(
    *required_permissions: str,
    message: Optional[str] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator enforcing authentication and canonical permissions before tool & DB execution.

    Preserves the wrapped function's signature and type annotations via `functools.wraps`
    so FastMCP schema generation and `Context` injection continue to work seamlessly.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(func)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Prompt-injection hardening (OWASP LLM01 / LLM06):
            # Strip any LLM-supplied org_id, user_id, or tenant_id arguments.
            stripped_keys = [k for k in UNTRUSTED_LLM_IDENTITY_FIELDS if k in kwargs]
            if stripped_keys:
                logger.warning(
                    "Prompt-injection hardening: stripped untrusted identity argument(s) %s from tool '%s'.",
                    stripped_keys,
                    func.__name__,
                )
                for key in stripped_keys:
                    kwargs.pop(key, None)

            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            arguments = bound.arguments

            session_token = arguments.get("session_token")
            ctx = arguments.get("ctx")
            effective_token = session_token or extract_token_from_mcp_context(ctx)

            # When a verified session token is present, ignore any LLM-supplied user_context
            # so prompt injection cannot override the authenticated caller or tenant scope.
            user_context = None if effective_token else arguments.get("user_context")
            if effective_token and arguments.get("user_context") is not None:
                logger.warning(
                    "Prompt-injection hardening: ignored untrusted 'user_context' because a verified session token is present in '%s'.",
                    func.__name__,
                )
                if "user_context" in kwargs:
                    kwargs["user_context"] = None

            try:
                verified_ctx = resolve_verified_user_context(
                    user_context=user_context,
                    session_token=effective_token,
                )
            except AuthVerificationError as exc:
                return error_response(exc.code, exc.message)

            if required_permissions and not any(
                has_permission(verified_ctx, perm) for perm in required_permissions
            ):
                err_msg = message or (
                    f"Permission denied for '{func.__name__}'. "
                    f"Requires one of: {', '.join(required_permissions)}."
                )
                return PermissionDeniedError(
                    message=err_msg,
                    required_permissions=required_permissions,
                    tool_name=func.__name__,
                    role=verified_ctx.get("role"),
                ).to_response()

            reset_token = _REQUEST_VERIFIED_CTX.set(verified_ctx)
            try:
                return func(*args, **kwargs)
            finally:
                _REQUEST_VERIFIED_CTX.reset(reset_token)

        return wrapper

    return decorator
