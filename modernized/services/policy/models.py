"""
Policy Service — Domain Models

Clean Pydantic domain model for the Policy bounded context, mirroring the
structure of ``claims/models.py``: enums, a validated input model, a domain
entity, and an explicit status state machine.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

# Upper bound on coverage a single policy can carry (EUR).
MAX_COVERAGE_AMOUNT = 50_000_000.0


class PolicyType(str, Enum):
    AUTO = "auto"
    HOME = "home"
    TRAVEL = "travel"
    HEALTH = "health"
    LIABILITY = "liability"
    LIFE = "life"


class PolicyStatus(str, Enum):
    """State machine for the policy lifecycle."""
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    RENEWED = "renewed"


# Valid state transitions (state machine).
VALID_TRANSITIONS: dict[PolicyStatus, set[PolicyStatus]] = {
    PolicyStatus.DRAFT: {PolicyStatus.ACTIVE, PolicyStatus.CANCELLED},
    PolicyStatus.ACTIVE: {
        PolicyStatus.SUSPENDED,
        PolicyStatus.CANCELLED,
        PolicyStatus.EXPIRED,
        PolicyStatus.RENEWED,
    },
    PolicyStatus.SUSPENDED: {PolicyStatus.ACTIVE, PolicyStatus.CANCELLED},
    PolicyStatus.EXPIRED: {PolicyStatus.RENEWED},
    PolicyStatus.RENEWED: {PolicyStatus.ACTIVE},
    PolicyStatus.CANCELLED: set(),
}

# Base annual premium rate per policy type (fraction of coverage amount).
BASE_PREMIUM_RATE: dict[PolicyType, float] = {
    PolicyType.AUTO: 0.04,
    PolicyType.HOME: 0.02,
    PolicyType.TRAVEL: 0.06,
    PolicyType.HEALTH: 0.05,
    PolicyType.LIABILITY: 0.03,
    PolicyType.LIFE: 0.015,
}


class PolicyApplication(BaseModel):
    """Input model for creating a policy — fully validated at the boundary."""
    customer_id: str = Field(min_length=1)
    policy_type: PolicyType
    coverage_amount: float = Field(gt=0, le=MAX_COVERAGE_AMOUNT)
    start_date: datetime
    end_date: datetime

    @field_validator("coverage_amount")
    @classmethod
    def coverage_rounded(cls, v: float) -> float:
        return round(v, 2)

    @model_validator(mode="after")
    def end_after_start(self) -> "PolicyApplication":
        if self.end_date <= self.start_date:
            raise ValueError("Policy end_date must be after start_date")
        return self


class Policy(BaseModel):
    """Policy domain entity."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    policy_number: str = Field(
        default_factory=lambda: f"POL-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"
    )
    customer_id: str
    policy_type: PolicyType
    start_date: datetime
    end_date: datetime
    premium_amount: float
    coverage_amount: float
    status: PolicyStatus = PolicyStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def transition_to(self, new_status: PolicyStatus) -> None:
        """Enforce state machine transitions."""
        valid_next = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in valid_next:
            raise ValueError(
                f"Invalid transition: {self.status.value} → {new_status.value}. "
                f"Valid transitions: {[s.value for s in valid_next]}"
            )
        self.status = new_status
        self.updated_at = datetime.now()


class CoverageResult(BaseModel):
    """Result of a coverage verification check."""
    covered: bool
    reason: Optional[str] = None
    remaining_coverage: Optional[float] = None


def calculate_premium(policy_type: PolicyType, coverage_amount: float) -> float:
    """Compute the gross annual premium (base rate + 21% insurance tax)."""
    base = coverage_amount * BASE_PREMIUM_RATE[policy_type]
    return round(base * 1.21, 2)
