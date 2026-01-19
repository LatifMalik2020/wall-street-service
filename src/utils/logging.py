"""Structured logging configuration."""

import os
import logging
import structlog
from typing import Optional
from contextvars import ContextVar

# Context variables for request tracking
request_id_var: ContextVar[str] = ContextVar("request_id", default="unknown")
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


def add_request_context(
    logger: logging.Logger, method_name: str, event_dict: dict
) -> dict:
    """Add request context to log entries."""
    event_dict["request_id"] = request_id_var.get()
    user_id = user_id_var.get()
    if user_id:
        event_dict["user_id"] = user_id
    return event_dict


def set_request_context(request_id: str, user_id: Optional[str] = None) -> None:
    """Set request context for logging."""
    request_id_var.set(request_id)
    if user_id:
        user_id_var.set(user_id)


def clear_request_context() -> None:
    """Clear request context."""
    request_id_var.set("unknown")
    user_id_var.set(None)


# Configure structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_request_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.DEBUG if os.getenv("LOG_LEVEL", "info").lower() == "debug" else logging.INFO
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

# Create logger instance
logger = structlog.get_logger("wall-street-service")
