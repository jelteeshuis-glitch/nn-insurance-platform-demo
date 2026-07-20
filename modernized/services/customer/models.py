"""
Customer Service — Domain Models (GDPR Compliant)

Pydantic domain model for the Customer bounded context, mirroring the Claims
template. PII (BSN, email, phone, address) is validated at the boundary and
stored only in encrypted form on the :class:`Customer` entity — plaintext PII
never persists (contrast the legacy schema which stores BSN/email in cleartext).
"""
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")


class ConsentType(str, Enum):
    """GDPR consent categories."""
    ESSENTIAL = "essential"      # Required for service delivery
    MARKETING = "marketing"      # Email/SMS marketing
    ANALYTICS = "analytics"      # Usage analytics
    PROFILING = "profiling"      # Automated profiling
    THIRD_PARTY = "third_party"  # Data sharing with partners


def validate_bsn(bsn: str) -> bool:
    """Validate a Dutch BSN using the 11-proef (elfproef) checksum.

    Stronger than the legacy length-only check.
    """
    digits = str(bsn).strip()
    if len(digits) != 9 or not digits.isdigit():
        return False
    weights = [9, 8, 7, 6, 5, 4, 3, 2, -1]
    total = sum(int(d) * w for d, w in zip(digits, weights, strict=True))
    return total % 11 == 0


class CustomerConsent(BaseModel):
    """Granular consent record per GDPR Art. 7."""
    consent_type: ConsentType
    granted: bool
    granted_at: Optional[str] = None
    withdrawn_at: Optional[str] = None
    purpose: str = ""
    version: str = "1.0"


class CustomerRegistration(BaseModel):
    """Boundary input model — plaintext PII, validated then encrypted."""
    bsn: str
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    birth_date: Optional[str] = None

    @field_validator("bsn")
    @classmethod
    def bsn_valid(cls, v: str) -> str:
        if not validate_bsn(v):
            raise ValueError("Invalid BSN (failed 11-proef checksum)")
        return v

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email address")
        return v


class Customer(BaseModel):
    """Customer entity with GDPR-aware, encrypted-at-rest PII."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    bsn_encrypted: str
    first_name: str
    last_name: str
    email_encrypted: str
    phone_encrypted: Optional[str] = None
    address_encrypted: Optional[str] = None
    birth_date: Optional[str] = None
    consents: list[CustomerConsent] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    is_deleted: bool = False
    deletion_requested_at: Optional[str] = None

    def has_consent(self, consent_type: ConsentType) -> bool:
        """Return ``True`` if the customer currently grants ``consent_type``."""
        for c in self.consents:
            if c.consent_type == consent_type:
                return c.granted
        return False


class ConsentUpdate(BaseModel):
    """Input model for granting/withdrawing a consent."""
    consent_type: ConsentType
    granted: bool
    purpose: str = Field(default="", max_length=500)
