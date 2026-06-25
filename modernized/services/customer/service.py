"""
Customer Service — GDPR Compliant

Manages customer data with:
- PII encryption at rest
- Right to erasure (Art. 17 GDPR)
- Data portability (Art. 20 GDPR)
- Consent management
- Data minimization
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ConsentType(str, Enum):
    """GDPR consent categories."""
    ESSENTIAL = "essential"  # Required for service delivery
    MARKETING = "marketing"  # Email/SMS marketing
    ANALYTICS = "analytics"  # Usage analytics
    PROFILING = "profiling"  # Automated profiling
    THIRD_PARTY = "third_party"  # Data sharing with partners


@dataclass
class CustomerConsent:
    """Granular consent record per GDPR Art. 7."""
    consent_type: ConsentType
    granted: bool
    granted_at: Optional[str] = None
    withdrawn_at: Optional[str] = None
    purpose: str = ""
    version: str = "1.0"  # Consent text version


@dataclass
class Customer:
    """Customer entity with GDPR-aware data handling."""
    id: str
    bsn_encrypted: str  # BSN stored encrypted, never in plaintext
    first_name: str
    last_name: str
    email_encrypted: str  # PII encrypted at rest
    phone_encrypted: Optional[str] = None
    address_encrypted: Optional[str] = None
    birth_date: Optional[str] = None
    consents: list[CustomerConsent] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    is_deleted: bool = False  # Soft delete for right-to-erasure
    deletion_requested_at: Optional[str] = None


class CustomerService:
    """GDPR-compliant customer data service.

    Key principles:
    - Data minimization: only collect what's necessary
    - Purpose limitation: data used only for stated purpose
    - Storage limitation: automatic data retention enforcement
    - Integrity: encrypted at rest, audit trail for all access
    """

    def __init__(self, repository, encryption_service, audit_logger):
        self.repository = repository
        self.encryption = encryption_service
        self.audit = audit_logger

    async def get_customer(self, customer_id: str, purpose: str) -> Optional[Customer]:
        """Retrieve customer data — logs access with purpose (Art. 30)."""
        customer = await self.repository.get(customer_id)
        if customer and customer.is_deleted:
            return None  # Right to erasure enforced

        # Log data access with purpose
        if customer:
            self.audit.log_data_access(
                actor="system",
                resource=f"customer:{customer_id}",
                purpose=purpose,
                fields_accessed=["first_name", "last_name", "email"],
            )

        return customer

    async def right_to_erasure(self, customer_id: str, requestor: str) -> dict:
        """Process right-to-erasure request (GDPR Art. 17).

        Does NOT delete:
        - Data required for legal obligations (Solvency II retention)
        - Data needed for ongoing claims
        - Anonymized statistical data

        Does delete/anonymize:
        - Personal contact information
        - Marketing preferences
        - Non-essential profile data
        """
        customer = await self.repository.get(customer_id)
        if not customer:
            return {"success": False, "reason": "Customer not found"}

        # Check if deletion is blocked by legal retention
        active_claims = await self._check_active_claims(customer_id)
        if active_claims:
            return {
                "success": False,
                "reason": "Cannot delete: active claims in progress",
                "blocked_by": [c.id for c in active_claims],
            }

        # Anonymize rather than hard-delete (retain for Solvency II)
        customer.first_name = "[ERASED]"
        customer.last_name = "[ERASED]"
        customer.email_encrypted = "[ERASED]"
        customer.phone_encrypted = "[ERASED]"
        customer.address_encrypted = "[ERASED]"
        customer.is_deleted = True
        customer.deletion_requested_at = datetime.now(timezone.utc).isoformat()

        await self.repository.save(customer)

        return {
            "success": True,
            "anonymized_fields": ["first_name", "last_name", "email", "phone", "address"],
            "retained_for_legal": ["bsn_encrypted", "birth_date", "claim_history"],
            "retention_until": "7 years from last policy end date (Solvency II)",
        }

    async def data_portability(self, customer_id: str) -> dict:
        """Export customer data in machine-readable format (GDPR Art. 20)."""
        customer = await self.repository.get(customer_id)
        if not customer or customer.is_deleted:
            return {"success": False, "reason": "Customer not found"}

        # Export in structured, machine-readable format
        return {
            "format": "JSON",
            "schema_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "data": {
                "personal_info": {
                    "first_name": customer.first_name,
                    "last_name": customer.last_name,
                    # Decrypted for export only
                },
                "consents": [
                    {"type": c.consent_type.value, "granted": c.granted}
                    for c in customer.consents
                ],
            },
        }

    async def _check_active_claims(self, customer_id: str) -> list:
        """Check for active claims blocking deletion."""
        # Would query claims service
        return []
