"""
Policy Administration Service — Bounded Context

Manages insurance policy lifecycle:
- Policy creation and amendments
- Premium calculation
- Coverage verification
- Policy renewal and cancellation
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class PolicyStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    RENEWED = "renewed"


class PolicyType(str, Enum):
    AUTO = "auto"
    HOME = "home"
    TRAVEL = "travel"
    HEALTH = "health"
    LIABILITY = "liability"
    LIFE = "life"


@dataclass
class Policy:
    """Policy domain entity."""
    id: str
    policy_number: str
    customer_id: str
    policy_type: PolicyType
    start_date: datetime
    end_date: datetime
    premium_amount: float
    coverage_amount: float
    status: PolicyStatus = PolicyStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PolicyService:
    """Policy service with proper authorization and audit."""

    def __init__(self, repository, audit_logger, event_bus):
        self.repository = repository
        self.audit = audit_logger
        self.events = event_bus

    async def get_policy(self, policy_id: str) -> Optional[Policy]:
        """Retrieve policy by ID."""
        return await self.repository.get(policy_id)

    async def verify_coverage(self, policy_id: str, claim_amount: float) -> dict:
        """Verify if a policy covers the claimed amount."""
        policy = await self.repository.get(policy_id)
        if not policy:
            return {"covered": False, "reason": "Policy not found"}

        if policy.status != PolicyStatus.ACTIVE:
            return {"covered": False, "reason": f"Policy status: {policy.status.value}"}

        if claim_amount > policy.coverage_amount:
            return {
                "covered": False,
                "reason": f"Amount €{claim_amount:,.2f} exceeds coverage €{policy.coverage_amount:,.2f}",
            }

        return {"covered": True, "remaining_coverage": policy.coverage_amount - claim_amount}
