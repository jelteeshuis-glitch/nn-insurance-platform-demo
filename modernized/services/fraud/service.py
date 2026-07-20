"""
Fraud Detection Service — Event Consumer (EU AI Act High-Risk)

Ports the opaque, inline ``ClaimsProcessor._check_fraud`` rules from
``legacy/src/claims.py`` into a dedicated, auditable service. In the legacy
system fraud scoring ran synchronously inside claim submission with no audit
trail and no explainability, violating EU AI Act record-keeping requirements
(ADR-004).

Here fraud assessment is a downstream consumer of the ``claim.submitted`` event.
Every inference is audited with its explanation (feature contributions), and a
high score publishes ``fraud.flagged`` for the Claims service to consume
(ADR-002 event table).
"""
from dataclasses import dataclass, field

from governance.audit import AuditEntry, AuditEventType, AuditLogger, RiskLevel

from ...shared.events import DomainEvent, EventBus

# Rule configuration — explicit and auditable (contrast legacy hidden rules).
HIGH_AMOUNT_THRESHOLD = 100_000.0
SUSPICIOUS_KEYWORDS = ("brand", "nieuw", "gestolen")
FLAG_THRESHOLD = 0.7


@dataclass
class FraudAssessment:
    """Explainable result of a fraud scoring run (EU AI Act Art. 13)."""

    claim_id: str
    score: float
    flagged: bool
    reasons: list[str] = field(default_factory=list)
    contributions: dict[str, float] = field(default_factory=dict)


class FraudDetectionService:
    """Rule-based, explainable fraud scoring with full audit trail."""

    MODEL_ID = "fraud_detection_card"

    def __init__(self, audit_logger: AuditLogger, event_bus: EventBus):
        self.audit = audit_logger
        self.events = event_bus

    def assess(self, claim_id: str, amount: float, description: str) -> FraudAssessment:
        """Score a claim for fraud risk. Pure, deterministic, explainable."""
        contributions: dict[str, float] = {}
        reasons: list[str] = []

        if amount > HIGH_AMOUNT_THRESHOLD:
            contributions["high_amount"] = 0.3
            reasons.append(f"amount €{amount:,.2f} exceeds €{HIGH_AMOUNT_THRESHOLD:,.0f}")

        description_lower = (description or "").lower()
        keyword_hits = [k for k in SUSPICIOUS_KEYWORDS if k in description_lower]
        if keyword_hits:
            contributions["suspicious_keywords"] = round(0.15 * len(keyword_hits), 2)
            reasons.append(f"suspicious keywords: {', '.join(keyword_hits)}")

        score = min(round(sum(contributions.values()), 2), 1.0)
        flagged = score >= FLAG_THRESHOLD

        return FraudAssessment(
            claim_id=claim_id,
            score=score,
            flagged=flagged,
            reasons=reasons,
            contributions=contributions,
        )

    async def on_claim_submitted(self, event: DomainEvent) -> None:
        """Consume ``claim.submitted`` — assess and flag if high risk."""
        payload = event.payload
        assessment = self.assess(
            claim_id=payload.get("claim_id", ""),
            amount=float(payload.get("amount", 0.0)),
            description=str(payload.get("description", "")),
        )

        # EU AI Act Art. 12 — record-keeping for every inference.
        self.audit.log(AuditEntry(
            event_type=AuditEventType.MODEL_INFERENCE,
            actor="fraud_detection_service",
            actor_role="system",
            resource=f"claim:{assessment.claim_id}",
            action=f"Fraud assessment score={assessment.score:.2f}",
            outcome="success",
            risk_level=RiskLevel.HIGH,
            details={
                "model_id": self.MODEL_ID,
                "score": assessment.score,
                "contributions": assessment.contributions,
                "reasons": assessment.reasons,
            },
        ))

        if assessment.flagged:
            await self.events.publish("fraud.flagged", {
                "claim_id": assessment.claim_id,
                "fraud_score": assessment.score,
                "reason": "; ".join(assessment.reasons) or "high fraud score",
            })
