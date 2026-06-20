"""Shared FastAPI dependencies."""

from fastapi import Header, Request


async def correlation_id(request: Request, x_correlation_id: str | None = Header(default=None)) -> str:
    """Return the request correlation ID."""
    return x_correlation_id or getattr(request.state, "correlation_id", "")
