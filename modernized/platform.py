"""
Platform Composition Root

Wires the five bounded contexts together for the in-process demo:
- Instantiates each service with an in-memory repository, a shared audit logger,
  and a shared event bus.
- Subscribes the cross-service event handlers described in ADR-002.

This is the single place that knows about all services; each service itself
stays decoupled and communicates only via domain events.
"""
import os
from dataclasses import dataclass

from governance.audit import AuditLogger

from .services.claims.models import Claim
from .services.claims.service import ClaimsService
from .services.customer.models import Customer
from .services.customer.service import CustomerService
from .services.fraud.service import FraudDetectionService
from .services.payments.bank import BankClient, SimulatedBankClient
from .services.payments.repository import PaymentRepository
from .services.payments.service import PaymentService
from .services.policy.models import Policy
from .services.policy.service import PolicyService
from .shared.encryption import EncryptionService, FernetEncryptionService
from .shared.events import EventBus
from .shared.notifications import NotificationService
from .shared.repository import InMemoryRepository


@dataclass
class Platform:
    """Container holding all composed services and shared infrastructure."""
    audit: AuditLogger
    events: EventBus
    notifications: NotificationService
    claims: ClaimsService
    policy: PolicyService
    payments: PaymentService
    customer: CustomerService
    fraud: FraudDetectionService


def build_platform(
    bank_client: BankClient | None = None,
    encryption_service: EncryptionService | None = None,
) -> Platform:
    """Compose all services and wire the ADR-002 event subscriptions."""
    audit = AuditLogger()
    events = EventBus(service_name="nn-insurance-platform")
    notifications = NotificationService()

    if encryption_service is None:
        # A managed key (Azure Key Vault / secret store) in production; a
        # freshly generated ephemeral key for the demo when unset.
        env_key = os.environ.get("ENCRYPTION_KEY") or None
        encryption_service = FernetEncryptionService(key=env_key)

    policy = PolicyService(
        repository=InMemoryRepository[Policy](),
        audit_logger=audit,
        event_bus=events,
    )
    customer = CustomerService(
        repository=InMemoryRepository[Customer](),
        encryption_service=encryption_service,
        audit_logger=audit,
    )
    fraud = FraudDetectionService(audit_logger=audit, event_bus=events)
    payments = PaymentService(
        repository=PaymentRepository(),
        bank_client=bank_client or SimulatedBankClient(),
        audit_logger=audit,
        event_bus=events,
    )
    claims = ClaimsService(
        repository=InMemoryRepository[Claim](),
        audit_logger=audit,
        event_bus=events,
        policy_service=policy,
        fraud_service=fraud,
    )

    # ADR-002 event table — inter-service subscriptions.
    events.subscribe("claim.submitted", fraud.on_claim_submitted)
    events.subscribe("claim.submitted", notifications.handle_event)
    events.subscribe("claim.approved", payments.on_claim_approved)
    events.subscribe("claim.approved", notifications.handle_event)
    events.subscribe("claim.rejected", notifications.handle_event)
    events.subscribe("fraud.flagged", claims.on_fraud_flagged)
    events.subscribe("payment.completed", claims.on_payment_completed)
    events.subscribe("payment.completed", notifications.handle_event)

    return Platform(
        audit=audit,
        events=events,
        notifications=notifications,
        claims=claims,
        policy=policy,
        payments=payments,
        customer=customer,
        fraud=fraud,
    )
