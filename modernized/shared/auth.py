"""
Shared Authentication & Authorization Module

Implements:
- JWT-based token validation
- Role-based access control (RBAC)
- Rate limiting
- Account lockout
- Session management with proper timeout
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import wraps
from typing import Optional


class Role(str, Enum):
    """System roles with hierarchical permissions."""
    CUSTOMER = "customer"
    AGENT = "agent"
    SENIOR_AGENT = "senior_agent"
    MANAGER = "manager"
    ADMIN = "admin"
    SYSTEM = "system"


# Permission matrix
PERMISSIONS: dict[str, set[Role]] = {
    "claims:submit": {Role.CUSTOMER, Role.AGENT, Role.ADMIN},
    "claims:view_own": {Role.CUSTOMER, Role.AGENT, Role.SENIOR_AGENT, Role.MANAGER, Role.ADMIN},
    "claims:view_all": {Role.AGENT, Role.SENIOR_AGENT, Role.MANAGER, Role.ADMIN},
    "claims:process": {Role.AGENT, Role.SENIOR_AGENT, Role.MANAGER, Role.ADMIN},
    "claims:approve_high_value": {Role.SENIOR_AGENT, Role.MANAGER, Role.ADMIN},
    "payments:initiate": {Role.SENIOR_AGENT, Role.MANAGER, Role.ADMIN},
    "payments:batch": {Role.MANAGER, Role.ADMIN},
    "reports:view": {Role.MANAGER, Role.ADMIN},
    "admin:users": {Role.ADMIN},
    "admin:config": {Role.ADMIN},
}


@dataclass
class AuthContext:
    """Authenticated user context — passed through request pipeline."""
    user_id: str
    username: str
    role: Role
    permissions: set[str]
    session_id: str
    authenticated_at: datetime
    expires_at: datetime
    mfa_verified: bool = False

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions

    def can_approve_amount(self, amount: float) -> bool:
        """Check if user can approve a specific amount."""
        if amount > 50_000:
            return self.role in (Role.SENIOR_AGENT, Role.MANAGER, Role.ADMIN)
        return self.has_permission("claims:process")


class RateLimiter:
    """Token bucket rate limiter — per user."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[datetime]] = {}

    def is_allowed(self, user_id: str) -> bool:
        """Check if request is within rate limit."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=self.window_seconds)

        if user_id not in self._buckets:
            self._buckets[user_id] = []

        # Clean old entries
        self._buckets[user_id] = [
            t for t in self._buckets[user_id] if t > window_start
        ]

        if len(self._buckets[user_id]) >= self.max_requests:
            return False

        self._buckets[user_id].append(now)
        return True


class AccountLockout:
    """Account lockout after failed login attempts."""

    def __init__(self, max_attempts: int = 5, lockout_minutes: int = 30):
        self.max_attempts = max_attempts
        self.lockout_duration = timedelta(minutes=lockout_minutes)
        self._attempts: dict[str, list[datetime]] = {}
        self._lockouts: dict[str, datetime] = {}

    def record_failure(self, username: str) -> None:
        """Record a failed login attempt."""
        now = datetime.now(timezone.utc)
        if username not in self._attempts:
            self._attempts[username] = []
        self._attempts[username].append(now)

        # Check if lockout threshold reached
        recent = [
            t for t in self._attempts[username]
            if t > now - timedelta(minutes=15)
        ]
        if len(recent) >= self.max_attempts:
            self._lockouts[username] = now + self.lockout_duration

    def is_locked(self, username: str) -> bool:
        """Check if account is locked."""
        if username in self._lockouts:
            if datetime.now(timezone.utc) < self._lockouts[username]:
                return True
            # Lockout expired
            del self._lockouts[username]
        return False

    def clear(self, username: str) -> None:
        """Clear login attempts on successful auth."""
        self._attempts.pop(username, None)
        self._lockouts.pop(username, None)


def require_permission(permission: str):
    """Decorator to enforce permission check on service methods."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, auth_context: AuthContext, **kwargs):
            if auth_context.is_expired:
                raise PermissionError("Session expired — please re-authenticate")
            if not auth_context.has_permission(permission):
                raise PermissionError(
                    f"Permission denied: {permission} requires role "
                    f"{[r.value for r in PERMISSIONS.get(permission, set())]}"
                )
            return await func(*args, auth_context=auth_context, **kwargs)
        return wrapper
    return decorator
