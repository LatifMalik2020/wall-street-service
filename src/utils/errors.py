"""Custom exceptions for Wall Street Service."""

from typing import Optional


class WallStreetError(Exception):
    """Base exception for Wall Street Service."""

    def __init__(
        self,
        message: str,
        error_code: str = "WALL_STREET_ERROR",
        status_code: int = 500,
        details: Optional[dict] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        result = {
            "code": self.error_code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


class NotFoundError(WallStreetError):
    """Resource not found."""

    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            error_code="NOT_FOUND",
            status_code=404,
            details={"resource": resource, "identifier": identifier},
        )


class ValidationError(WallStreetError):
    """Validation error."""

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=400,
            details={"field": field} if field else {},
        )


class RateLimitError(WallStreetError):
    """Rate limit exceeded."""

    def __init__(self, limit: int, window_seconds: int):
        super().__init__(
            message=f"Rate limit exceeded: {limit} requests per {window_seconds} seconds",
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"limit": limit, "windowSeconds": window_seconds},
        )


class ExternalAPIError(WallStreetError):
    """External API error."""

    def __init__(self, api_name: str, message: str):
        super().__init__(
            message=f"External API error ({api_name}): {message}",
            error_code="EXTERNAL_API_ERROR",
            status_code=502,
            details={"api": api_name},
        )


class AuthenticationError(WallStreetError):
    """Authentication error."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            error_code="UNAUTHORIZED",
            status_code=401,
        )


class ConflictError(WallStreetError):
    """Conflict error (e.g., duplicate resource)."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="CONFLICT",
            status_code=409,
        )
