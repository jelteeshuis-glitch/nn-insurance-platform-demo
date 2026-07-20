"""
Policy Administration Service — Application Layer

Bounded context managing the insurance policy lifecycle:
- Policy creation and premium calculation
- Coverage verification (consumed by the Claims service)
- Activation, suspension, cancellation and renewal (state machine enforced)

Cross-cutting concerns mirror the Claims template:
- Input validation via Pydantic (``PolicyApplication``)
- RBAC authorization via ``shared.auth``
- Immutable audit logging via ``governance.audit``
- Event publishing via ``shared.events`` (decoupled from consumers)
"""
from typing import Optional

from governance.audit import AuditEntry, AuditEventType, AuditLogger

from ...shared.auth import authorize
from ...shared.events import EventBus
from ...shared.repository import Repository
from .models import (
    CoverageResult,
    Policy,
    PolicyApplication,
    PolicyStatus,
    calculate_premium,
)


class PolicyService:
    """Policy service — single responsibility, RBAC + audit + events."""

    def __init__(
        self,
        repository: Repository[Policy],
        audit_logger: AuditLogger,
        event_bus: EventBus,
    ):
        self.repository = repository
        self.audit = audit_logger
        self.events = event_bus

    async def create_policy(
        self, application: PolicyApplication, actor: str, actor_role: str
    ) -> Policy:
        """Create a policy in DRAFT state with a computed premium."""
        authorize(actor_role, "policy:create")

        premium = calculate_premium(application.policy_type, application.coverage_amount)
        policy = Policy(
            customer_id=application.customer_id,
            policy_type=application.policy_type,
            start_date=application.start_date,
            end_date=application.end_date,
            coverage_amount=application.coverage_amount,
            premium_amount=premium,
        )
        await self.repository.save(policy)

        self.audit.log(AuditEntry(
            event_type=AuditEventType.DATA_WRITE,
            actor=actor,
            actor_role=actor_role,
            resource=f"policy:{policy.id}",
            action=f"Created policy {policy.policy_number} ({policy.policy_type.value})",
            outcome="success",
            details={
                "policy_number": policy.policy_number,
                "coverage_amount": policy.coverage_amount,
                "premium_amount": policy.premium_amount,
            },
            data_subjects=[application.customer_id],
        ))
        await self.events.publish("policy.created", {
            "policy_id": policy.id,
            "policy_number": policy.policy_number,
            "customer_id": policy.customer_id,
        })
        return policy

    async def get_policy(self, policy_id: str) -> Optional[Policy]:
        """Retrieve a policy by ID (used by the Claims service)."""
        return await self.repository.get(policy_id)

    async def activate_policy(self, policy_id: str, actor: str, actor_role: str) -> Policy:
        """Activate a DRAFT or SUSPENDED policy."""
        authorize(actor_role, "policy:manage")
        policy = await self._require(policy_id)
        policy.transition_to(PolicyStatus.ACTIVE)
        await self.repository.save(policy)
        self._audit(policy, actor, actor_role, "Activated")
        await self.events.publish("policy.activated", {"policy_id": policy.id})
        return policy

    async def suspend_policy(
        self, policy_id: str, reason: str, actor: str, actor_role: str
    ) -> Policy:
        """Suspend an active policy (e.g. non-payment)."""
        authorize(actor_role, "policy:manage")
        policy = await self._require(policy_id)
        policy.transition_to(PolicyStatus.SUSPENDED)
        await self.repository.save(policy)
        self._audit(policy, actor, actor_role, f"Suspended: {reason}")
        await self.events.publish("policy.suspended", {"policy_id": policy.id})
        return policy

    async def cancel_policy(
        self, policy_id: str, reason: str, actor: str, actor_role: str
    ) -> Policy:
        """Cancel a policy (terminal)."""
        authorize(actor_role, "policy:manage")
        policy = await self._require(policy_id)
        policy.transition_to(PolicyStatus.CANCELLED)
        await self.repository.save(policy)
        self._audit(policy, actor, actor_role, f"Cancelled: {reason}")
        await self.events.publish("policy.cancelled", {"policy_id": policy.id})
        return policy

    async def verify_coverage(self, policy_id: str, claim_amount: float) -> CoverageResult:
        """Verify whether an active policy covers the claimed amount."""
        policy = await self.repository.get(policy_id)
        if not policy:
            return CoverageResult(covered=False, reason="Policy not found")
        if policy.status != PolicyStatus.ACTIVE:
            return CoverageResult(
                covered=False, reason=f"Policy status: {policy.status.value}"
            )
        if claim_amount > policy.coverage_amount:
            return CoverageResult(
                covered=False,
                reason=(
                    f"Amount €{claim_amount:,.2f} exceeds "
                    f"coverage €{policy.coverage_amount:,.2f}"
                ),
            )
        return CoverageResult(
            covered=True,
            remaining_coverage=round(policy.coverage_amount - claim_amount, 2),
        )

    async def _require(self, policy_id: str) -> Policy:
        policy = await self.repository.get(policy_id)
        if not policy:
            raise ValueError(f"Policy {policy_id} not found")
        return policy

    def _audit(self, policy: Policy, actor: str, actor_role: str, action: str) -> None:
        self.audit.log(AuditEntry(
            event_type=AuditEventType.DATA_WRITE,
            actor=actor,
            actor_role=actor_role,
            resource=f"policy:{policy.id}",
            action=f"{action} policy {policy.policy_number}",
            outcome="success",
            details={"status": policy.status.value},
            data_subjects=[policy.customer_id],
        ))
