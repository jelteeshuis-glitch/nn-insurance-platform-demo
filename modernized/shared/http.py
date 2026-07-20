"""
Shared HTTP helpers for the per-service FastAPI apps.

Maps domain exceptions to HTTP status codes so route handlers stay thin and
free of try/except boilerplate.
"""
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


@dataclass
class Actor:
    """The authenticated caller, resolved from request headers."""
    actor: str
    role: str


def get_actor(request: Request) -> Actor:
    """Extract the caller identity/role from ``X-Actor`` / ``X-Actor-Role``."""
    return Actor(
        actor=request.headers.get("X-Actor", "anonymous"),
        role=request.headers.get("X-Actor-Role", "customer"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register domain-exception → HTTP status mappings on ``app``."""

    @app.exception_handler(PermissionError)
    async def _permission_denied(request: Request, exc: PermissionError):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _bad_request(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})
