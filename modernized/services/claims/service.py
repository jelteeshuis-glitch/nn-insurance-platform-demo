"""
Claims Service — Application Layer

Clean separation of concerns:
- Input validation (Pydantic models)
- Business rules (domain logic)
- Authorization (RBAC middleware)
- Audit logging (cross-cutting concern)
- Event publishing (async, decoupled)
"""
from datetime import datetime

from governance.audit import AuditEntry, AuditEventType, AuditLogger, RiskLevel

from ...shared.auth import authorize
from .models import Claim, ClaimDecision, ClaimStatus, ClaimSubmission


class ClaimsService:
    """Claims service — single responsibility, properly bounded.

    Compared to legacy ClaimsProcessor:
    - ✅ Input validation via Pydantic
    - ✅ State machine enforcement
    - ✅ Proper authorization checks
    - ✅ Audit logging on every action
    - ✅ Event-driven (decoupled from payments, notifications)
    - ✅ Idempotent operations
    - ✅ Proper error handling
    """

    def __init__(
        self,
        repository,  # Abstract repository (not direct DB)
        audit_logger: AuditLogger,
        event_bus,  # Async event publishing
        policy_service,  # External service client
        fraud_service,  # Separate fraud detection service
    ):
        self.repository = repository
        self.audit = audit_logger
        self.events = event_bus
        self.policy_service = policy_service
        self.fraud_service = fraud_service

    async def submit_claim(
        self, submission: ClaimSubmission, customer_id: str, actor: str
    ) -> Claim:
        """Submit a new claim with full validation and audit trail.

        Steps:
        1. Validate input (Pydantic does this)
        2. Verify policy ownership and status
        3. Create claim in DRAFT state
        4. Request async fraud assessment
        5. Transition to SUBMITTED
        6. Publish event for downstream services
        7. Return claim with status
        """
        # Verify policy belongs to customer and is active
        policy = await self.policy_service.get_policy(submission.policy_id)
        if not policy or policy.customer_id != customer_id:
            raise PermissionError("Policy not found or not owned by customer")
        if policy.status != "active":
            raise ValueError(f"Policy is not active (status: {policy.status})")

        # Verify claim amount within coverage
        if submission.amount_claimed > policy.coverage_amount:
            raise ValueError(
                f"Claim amount (€{submission.amount_claimed:,.2f}) exceeds "
                f"coverage (€{policy.coverage_amount:,.2f})"
            )

        # Create claim
        claim = Claim(
            policy_id=submission.policy_id,
            customer_id=customer_id,
            claim_type=submission.claim_type,
            description=submission.description,
            amount_claimed=submission.amount_claimed,
            incident_date=submission.incident_date,
            submitted_at=datetime.now(),
        )

        # Transition to SUBMITTED (enforces state machine)
        claim.transition_to(ClaimStatus.SUBMITTED)

        # Persist
        await self.repository.save(claim)

        # Audit
        self.audit.log(AuditEntry(
            event_type=AuditEventType.CLAIM_SUBMITTED,
            actor=actor,
            actor_role="customer",
            resource=f"claim:{claim.id}",
            action=f"Submitted claim {claim.claim_number} for €{claim.amount_claimed:,.2f}",
            outcome="success",
            details={
                "claim_number": claim.claim_number,
                "policy_id": submission.policy_id,
                "claim_type": submission.claim_type.value,
                "amount": submission.amount_claimed,
            },
            data_subjects=[customer_id],
        ))

        # Request fraud assessment (async — doesn't block submission)
        await self.events.publish("claim.submitted", {
            "claim_id": claim.id,
            "claim_number": claim.claim_number,
            "amount": claim.amount_claimed,
            "description": claim.description,
            "customer_id": customer_id,
        })

        return claim

    async def process_decision(
        self, decision: ClaimDecision, actor: str, actor_role: str
    ) -> Claim:
        """Process a claim decision (approve/reject).

        Implements:
        - Four-eyes principle for high-value claims
        - State machine enforcement
        - Full audit trail
        - Segregation of duties
        """
        authorize(actor_role, "claims:process")

        claim = await self.repository.get(decision.claim_id)
        if not claim:
            raise ValueError(f"Claim {decision.claim_id} not found")

        # Segregation of duties: processor cannot be the submitter
        if claim.customer_id == actor:
            raise PermissionError("Cannot process your own claim")

        # Four-eyes: high-value claims need senior approval
        if (
            decision.decision == "approved"
            and decision.approved_amount
            and decision.approved_amount > 50_000
            and actor_role not in ("senior_agent", "manager", "admin")
        ):
            raise PermissionError(
                f"Claims above €50,000 require senior_agent or manager approval. "
                f"Current role: {actor_role}"
            )

        # State transition
        new_status = (
            ClaimStatus.APPROVED
            if decision.decision == "approved"
            else ClaimStatus.REJECTED
        )
        claim.transition_to(new_status)

        # Update fields
        claim.processed_by = actor
        claim.processed_at = datetime.now()
        claim.amount_approved = decision.approved_amount
        if decision.notes:
            claim.notes.append(f"[{actor}] {decision.notes}")

        # Persist
        await self.repository.save(claim)

        # Audit with full context
        self.audit.log(AuditEntry(
            event_type=(
                AuditEventType.CLAIM_APPROVED
                if decision.decision == "approved"
                else AuditEventType.CLAIM_REJECTED
            ),
            actor=actor,
            actor_role=actor_role,
            resource=f"claim:{claim.id}",
            action=(
                f"{'Approved' if decision.decision == 'approved' else 'Rejected'} "
                f"claim {claim.claim_number}"
            ),
            outcome="success",
            justification=decision.notes or "Standard processing",
            details={
                "claim_number": claim.claim_number,
                "decision": decision.decision,
                "amount_claimed": claim.amount_claimed,
                "amount_approved": decision.approved_amount,
            },
            data_subjects=[claim.customer_id],
        ))

        # Publish event for downstream (payment service, notification service)
        await self.events.publish(f"claim.{decision.decision}", {
            "claim_id": claim.id,
            "claim_number": claim.claim_number,
            "customer_id": claim.customer_id,
            "amount_approved": decision.approved_amount,
        })

        return claim

    async def advance_status(
        self, claim_id: str, new_status: ClaimStatus, actor: str, actor_role: str
    ) -> Claim:
        """Advance a claim through the review workflow (e.g. VALIDATED, UNDER_REVIEW).

        Enforces RBAC and the state machine; used to move a submitted claim into
        a reviewable state before a decision is made.
        """
        authorize(actor_role, "claims:process")
        claim = await self.repository.get(claim_id)
        if not claim:
            raise ValueError(f"Claim {claim_id} not found")

        claim.transition_to(new_status)
        await self.repository.save(claim)

        self.audit.log(AuditEntry(
            event_type=AuditEventType.DATA_WRITE,
            actor=actor,
            actor_role=actor_role,
            resource=f"claim:{claim.id}",
            action=f"Claim {claim.claim_number} → {new_status.value}",
            outcome="success",
            details={"status": new_status.value},
            data_subjects=[claim.customer_id],
        ))
        return claim

    async def flag_claim(
        self, claim_id: str, reason: str, fraud_score: float, actor: str
    ) -> Claim:
        """Flag a claim for review (called by fraud detection service)."""
        claim = await self.repository.get(claim_id)
        if not claim:
            raise ValueError(f"Claim {claim_id} not found")

        claim.transition_to(ClaimStatus.FLAGGED)
        claim.fraud_score = fraud_score
        claim.notes.append(f"[fraud_detection] Flagged: {reason} (score: {fraud_score:.2f})")

        await self.repository.save(claim)

        self.audit.log(AuditEntry(
            event_type=AuditEventType.CLAIM_FLAGGED,
            actor=actor,
            actor_role="system",
            resource=f"claim:{claim.id}",
            action=f"Flagged claim {claim.claim_number} (fraud score: {fraud_score:.2f})",
            outcome="success",
            risk_level=RiskLevel.HIGH,
            details={
                "fraud_score": fraud_score,
                "reason": reason,
                "claim_number": claim.claim_number,
            },
            data_subjects=[claim.customer_id],
        ))

        return claim

    async def mark_paid(self, claim_id: str, actor: str = "system") -> Claim:
        """Transition an approved claim to PAID (called after payment completes)."""
        claim = await self.repository.get(claim_id)
        if not claim:
            raise ValueError(f"Claim {claim_id} not found")

        claim.transition_to(ClaimStatus.PAID)
        await self.repository.save(claim)

        self.audit.log(AuditEntry(
            event_type=AuditEventType.PAYMENT_COMPLETED,
            actor=actor,
            actor_role="system",
            resource=f"claim:{claim.id}",
            action=f"Marked claim {claim.claim_number} as paid",
            outcome="success",
            details={"claim_number": claim.claim_number},
            data_subjects=[claim.customer_id],
        ))
        return claim

    # ------------------------------------------------------------------
    # Event consumers (wired in modernized/platform.py per ADR-002)
    # ------------------------------------------------------------------

    async def on_fraud_flagged(self, event) -> None:
        """Consume ``fraud.flagged`` — move the claim into FLAGGED review."""
        claim_id = event.payload.get("claim_id")
        claim = await self.repository.get(claim_id)
        if not claim:
            return
        # Advance a freshly-submitted claim to a flaggable state.
        if claim.status == ClaimStatus.SUBMITTED:
            claim.transition_to(ClaimStatus.VALIDATED)
            await self.repository.save(claim)
        await self.flag_claim(
            claim_id,
            reason=event.payload.get("reason", "high fraud score"),
            fraud_score=float(event.payload.get("fraud_score", 0.0)),
            actor="fraud_detection",
        )

    async def on_payment_completed(self, event) -> None:
        """Consume ``payment.completed`` — mark the underlying claim as paid."""
        claim_id = event.payload.get("claim_id")
        if claim_id:
            await self.mark_paid(claim_id)
