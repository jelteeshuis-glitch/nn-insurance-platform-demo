"""
Customer Service — Application Layer (GDPR Compliant)

Bounded context managing customer master data:
- Registration with PII encrypted at rest (ADR-005)
- Purpose-logged data access (GDPR Art. 30)
- Consent management (Art. 7)
- Right to erasure (Art. 17) and data portability (Art. 20)

Cross-cutting concerns mirror the Claims template: input validation (Pydantic),
RBAC authorization, and immutable audit logging via ``governance.audit``.
"""
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from governance.audit import AuditEntry, AuditEventType, AuditLogger

from ...shared.auth import authorize
from ...shared.encryption import EncryptionService
from ...shared.repository import Repository
from .models import (
    ConsentType,
    ConsentUpdate,
    Customer,
    CustomerConsent,
    CustomerRegistration,
)


class CustomerService:
    """GDPR-compliant customer data service."""

    def __init__(
        self,
        repository: Repository[Customer],
        encryption_service: EncryptionService,
        audit_logger: AuditLogger,
        active_claims_lookup: Optional[Callable[[str], Awaitable[list]]] = None,
    ):
        self.repository = repository
        self.encryption = encryption_service
        self.audit = audit_logger
        self.active_claims_lookup = active_claims_lookup

    async def register_customer(
        self, registration: CustomerRegistration, actor: str, actor_role: str
    ) -> Customer:
        """Register a customer, encrypting all PII before persistence."""
        authorize(actor_role, "customer:register")

        customer = Customer(
            bsn_encrypted=self.encryption.encrypt(registration.bsn),
            first_name=registration.first_name,
            last_name=registration.last_name,
            email_encrypted=self.encryption.encrypt(registration.email),
            phone_encrypted=(
                self.encryption.encrypt(registration.phone)
                if registration.phone else None
            ),
            address_encrypted=(
                self.encryption.encrypt(registration.address)
                if registration.address else None
            ),
            birth_date=registration.birth_date,
            consents=[
                CustomerConsent(
                    consent_type=ConsentType.ESSENTIAL,
                    granted=True,
                    granted_at=datetime.now(timezone.utc).isoformat(),
                    purpose="Service delivery",
                )
            ],
        )
        await self.repository.save(customer)

        self.audit.log(AuditEntry(
            event_type=AuditEventType.DATA_WRITE,
            actor=actor,
            actor_role=actor_role,
            resource=f"customer:{customer.id}",
            action=f"Registered customer {customer.first_name} {customer.last_name}",
            outcome="success",
            details={"consents": ["essential"]},
            data_subjects=[customer.id],
        ))
        return customer

    async def get_customer(
        self, customer_id: str, purpose: str, actor: str, actor_role: str
    ) -> Optional[Customer]:
        """Retrieve a customer — logs the access purpose (Art. 30)."""
        authorize(actor_role, "customer:read")

        customer = await self.repository.get(customer_id)
        if not customer or customer.is_deleted:
            return None

        self.audit.log(AuditEntry(
            event_type=AuditEventType.DATA_READ,
            actor=actor,
            actor_role=actor_role,
            resource=f"customer:{customer_id}",
            action="Read customer record",
            outcome="success",
            justification=purpose,
            details={"fields_accessed": ["first_name", "last_name", "email"]},
            data_subjects=[customer_id],
        ))
        return customer

    async def update_consent(
        self, customer_id: str, update: ConsentUpdate, actor: str, actor_role: str
    ) -> Customer:
        """Grant or withdraw a specific consent (Art. 7)."""
        authorize(actor_role, "customer:consent")

        customer = await self.repository.get(customer_id)
        if not customer or customer.is_deleted:
            raise ValueError(f"Customer {customer_id} not found")

        now = datetime.now(timezone.utc).isoformat()
        existing = next(
            (c for c in customer.consents if c.consent_type == update.consent_type),
            None,
        )
        if existing:
            existing.granted = update.granted
            existing.granted_at = now if update.granted else existing.granted_at
            existing.withdrawn_at = None if update.granted else now
            existing.purpose = update.purpose or existing.purpose
        else:
            customer.consents.append(CustomerConsent(
                consent_type=update.consent_type,
                granted=update.granted,
                granted_at=now if update.granted else None,
                withdrawn_at=None if update.granted else now,
                purpose=update.purpose,
            ))
        await self.repository.save(customer)

        self.audit.log(AuditEntry(
            event_type=AuditEventType.DATA_WRITE,
            actor=actor,
            actor_role=actor_role,
            resource=f"customer:{customer_id}",
            action=(
                f"{'Granted' if update.granted else 'Withdrew'} "
                f"consent {update.consent_type.value}"
            ),
            outcome="success",
            data_subjects=[customer_id],
        ))
        return customer

    async def right_to_erasure(
        self, customer_id: str, actor: str, actor_role: str
    ) -> dict:
        """Process a right-to-erasure request (Art. 17).

        Anonymizes personal contact data but retains records required for
        Solvency II (BSN, birth date, claim history). Blocked while claims are
        active.
        """
        authorize(actor_role, "customer:erase")

        customer = await self.repository.get(customer_id)
        if not customer or customer.is_deleted:
            return {"success": False, "reason": "Customer not found"}

        active_claims = await self._check_active_claims(customer_id)
        if active_claims:
            return {
                "success": False,
                "reason": "Cannot delete: active claims in progress",
                "blocked_by": active_claims,
            }

        customer.first_name = "[ERASED]"
        customer.last_name = "[ERASED]"
        customer.email_encrypted = self.encryption.encrypt("[ERASED]")
        customer.phone_encrypted = None
        customer.address_encrypted = None
        customer.is_deleted = True
        customer.deletion_requested_at = datetime.now(timezone.utc).isoformat()
        await self.repository.save(customer)

        self.audit.log(AuditEntry(
            event_type=AuditEventType.DATA_DELETE,
            actor=actor,
            actor_role=actor_role,
            resource=f"customer:{customer_id}",
            action="Right-to-erasure: anonymized personal data",
            outcome="success",
            justification="GDPR Art. 17 request",
            data_subjects=[customer_id],
        ))
        return {
            "success": True,
            "anonymized_fields": ["first_name", "last_name", "email", "phone", "address"],
            "retained_for_legal": ["bsn_encrypted", "birth_date", "claim_history"],
            "retention_until": "7 years from last policy end date (Solvency II)",
        }

    async def data_portability(
        self, customer_id: str, actor: str, actor_role: str
    ) -> dict:
        """Export customer data in a machine-readable format (Art. 20)."""
        authorize(actor_role, "customer:export")

        customer = await self.repository.get(customer_id)
        if not customer or customer.is_deleted:
            return {"success": False, "reason": "Customer not found"}

        self.audit.log(AuditEntry(
            event_type=AuditEventType.DATA_EXPORT,
            actor=actor,
            actor_role=actor_role,
            resource=f"customer:{customer_id}",
            action="Data portability export",
            outcome="success",
            justification="GDPR Art. 20 request",
            data_subjects=[customer_id],
        ))
        return {
            "success": True,
            "format": "JSON",
            "schema_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "data": {
                "personal_info": {
                    "first_name": customer.first_name,
                    "last_name": customer.last_name,
                    "email": self.encryption.decrypt(customer.email_encrypted),
                },
                "consents": [
                    {"type": c.consent_type.value, "granted": c.granted}
                    for c in customer.consents
                ],
            },
        }

    async def _check_active_claims(self, customer_id: str) -> list:
        """Check for active claims blocking deletion (via claims service)."""
        if self.active_claims_lookup:
            return await self.active_claims_lookup(customer_id)
        return []
