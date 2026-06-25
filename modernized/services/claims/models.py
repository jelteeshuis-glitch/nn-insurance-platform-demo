"""
Claims Service — Domain Models

Clean domain model using Pydantic for validation.
Bounded context: Claims lifecycle management.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ClaimType(str, Enum):
    AUTO = "auto"
    HOME = "home"
    TRAVEL = "travel"
    HEALTH = "health"
    LIABILITY = "liability"
    LIFE = "life"


class ClaimStatus(str, Enum):
    """State machine for claim lifecycle."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    VALIDATED = "validated"
    UNDER_REVIEW = "under_review"
    FLAGGED = "flagged"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"
    CLOSED = "closed"
    APPEALED = "appealed"


# Valid state transitions (state machine)
VALID_TRANSITIONS: dict[ClaimStatus, set[ClaimStatus]] = {
    ClaimStatus.DRAFT: {ClaimStatus.SUBMITTED},
    ClaimStatus.SUBMITTED: {ClaimStatus.VALIDATED, ClaimStatus.REJECTED},
    ClaimStatus.VALIDATED: {ClaimStatus.UNDER_REVIEW, ClaimStatus.FLAGGED},
    ClaimStatus.UNDER_REVIEW: {ClaimStatus.APPROVED, ClaimStatus.REJECTED, ClaimStatus.FLAGGED},
    ClaimStatus.FLAGGED: {ClaimStatus.UNDER_REVIEW, ClaimStatus.REJECTED},
    ClaimStatus.APPROVED: {ClaimStatus.PAID},
    ClaimStatus.REJECTED: {ClaimStatus.APPEALED, ClaimStatus.CLOSED},
    ClaimStatus.PAID: {ClaimStatus.CLOSED},
    ClaimStatus.APPEALED: {ClaimStatus.UNDER_REVIEW, ClaimStatus.CLOSED},
    ClaimStatus.CLOSED: set(),
}


class ClaimSubmission(BaseModel):
    """Input model for claim submission — fully validated."""
    policy_id: str
    claim_type: ClaimType
    description: str = Field(min_length=10, max_length=5000)
    amount_claimed: float = Field(gt=0, le=1_000_000)
    incident_date: datetime
    attachments: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("incident_date")
    @classmethod
    def incident_not_in_future(cls, v: datetime) -> datetime:
        if v > datetime.now():
            raise ValueError("Incident date cannot be in the future")
        return v

    @field_validator("amount_claimed")
    @classmethod
    def amount_reasonable(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Claim amount must be positive")
        return round(v, 2)


class Claim(BaseModel):
    """Domain entity — the core claim object."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    claim_number: str = Field(default_factory=lambda: f"CLM-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}")
    policy_id: str
    customer_id: str
    claim_type: ClaimType
    description: str
    amount_claimed: float
    amount_approved: Optional[float] = None
    status: ClaimStatus = ClaimStatus.DRAFT
    fraud_score: Optional[float] = None
    incident_date: datetime
    submitted_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    processed_by: Optional[str] = None
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def transition_to(self, new_status: ClaimStatus) -> None:
        """Enforce state machine transitions."""
        valid_next = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in valid_next:
            raise ValueError(
                f"Invalid transition: {self.status.value} → {new_status.value}. "
                f"Valid transitions: {[s.value for s in valid_next]}"
            )
        self.status = new_status
        self.updated_at = datetime.now()


class ClaimDecision(BaseModel):
    """Input model for claim processing decision."""
    claim_id: str
    decision: str = Field(pattern="^(approved|rejected)$")
    approved_amount: Optional[float] = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=2000)
    processed_by: str

    @field_validator("approved_amount")
    @classmethod
    def approved_amount_if_approved(cls, v, info):
        if info.data.get("decision") == "approved" and v is None:
            raise ValueError("Approved amount required for approval decision")
        return v
