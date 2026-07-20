"""
Payment Service — Domain Models (PCI-DSS Aware)

Pydantic domain model for the Payment bounded context, mirroring the Claims
template. Raw account numbers never enter the service: IBANs are validated at
the boundary (mod-97 checksum) and immediately tokenized, so only opaque
``iban_token`` values are stored (contrast ``legacy/src/payments.py`` which logs
raw IBANs and stores them in plaintext).
"""
import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class PaymentStatus(str, Enum):
    """State machine for the payment lifecycle."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethod(str, Enum):
    BANK_TRANSFER = "bank_transfer"
    SEPA_DIRECT = "sepa_direct"


VALID_TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
    PaymentStatus.PENDING: {PaymentStatus.PROCESSING, PaymentStatus.FAILED},
    PaymentStatus.PROCESSING: {PaymentStatus.COMPLETED, PaymentStatus.FAILED},
    PaymentStatus.COMPLETED: {PaymentStatus.REFUNDED},
    PaymentStatus.FAILED: {PaymentStatus.PENDING},
    PaymentStatus.REFUNDED: set(),
}


def validate_iban(iban: str) -> bool:
    """Validate an IBAN using the ISO 13616 mod-97 checksum.

    Stronger than the legacy regex-only check which accepted any well-formed
    string regardless of its check digits.
    """
    iban = iban.replace(" ", "").upper()
    if len(iban) < 15 or len(iban) > 34 or not iban[:2].isalpha():
        return False
    rearranged = iban[4:] + iban[:4]
    digits = ""
    for ch in rearranged:
        if ch.isdigit():
            digits += ch
        elif ch.isalpha():
            digits += str(ord(ch) - 55)
        else:
            return False
    return int(digits) % 97 == 1


def tokenize_iban(iban: str) -> str:
    """Produce a stable, non-reversible token for an IBAN (PCI-DSS).

    Production would exchange the IBAN for a vault token; the demo derives a
    deterministic surrogate so raw account data never lives in the service.
    """
    normalized = iban.replace(" ", "").upper()
    return "tok_" + hashlib.sha256(normalized.encode()).hexdigest()[:24]


class PaymentInstruction(BaseModel):
    """Boundary input model — accepts a raw IBAN, validated then tokenized."""
    claim_id: str = Field(min_length=1)
    amount: float = Field(gt=0, le=1_000_000)
    iban: str
    currency: str = Field(default="EUR", pattern="^[A-Z]{3}$")
    method: PaymentMethod = PaymentMethod.BANK_TRANSFER
    idempotency_key: str = Field(default_factory=lambda: str(uuid4()))

    @field_validator("amount")
    @classmethod
    def amount_rounded(cls, v: float) -> float:
        return round(v, 2)

    @field_validator("iban")
    @classmethod
    def iban_valid(cls, v: str) -> str:
        if not validate_iban(v):
            raise ValueError("Invalid IBAN (failed mod-97 checksum)")
        return v.replace(" ", "").upper()

    def to_payment(self) -> "Payment":
        """Create a domain :class:`Payment` with the IBAN tokenized."""
        return Payment(
            claim_id=self.claim_id,
            amount=self.amount,
            currency=self.currency,
            method=self.method,
            iban_token=tokenize_iban(self.iban),
            idempotency_key=self.idempotency_key,
        )


class Payment(BaseModel):
    """Payment domain entity — holds only a tokenized IBAN."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    claim_id: str
    amount: float
    currency: str = "EUR"
    method: PaymentMethod = PaymentMethod.BANK_TRANSFER
    iban_token: str = ""
    idempotency_key: str = Field(default_factory=lambda: str(uuid4()))
    status: PaymentStatus = PaymentStatus.PENDING
    bank_reference: Optional[str] = None
    error: Optional[str] = None
    refunded_amount: float = 0.0
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    processed_at: Optional[str] = None

    def transition_to(self, new_status: PaymentStatus) -> None:
        """Enforce state machine transitions."""
        valid_next = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in valid_next:
            raise ValueError(
                f"Invalid transition: {self.status.value} → {new_status.value}. "
                f"Valid transitions: {[s.value for s in valid_next]}"
            )
        self.status = new_status


class RefundRequest(BaseModel):
    """Input model for a refund."""
    payment_id: str = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=500)
    amount: Optional[float] = Field(default=None, gt=0)
