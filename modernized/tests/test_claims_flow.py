"""
Claims Service — application-layer & event-flow tests.

Complements test_claims_service.py (which covers models) by exercising the
ClaimsService business rules, RBAC, audit trail, and the end-to-end
event-driven flow wired in modernized/platform.py.
"""
from datetime import datetime, timedelta

import pytest

from modernized.platform import build_platform
from modernized.services.claims.models import (
    ClaimDecision,
    ClaimStatus,
    ClaimSubmission,
    ClaimType,
)
from modernized.services.payments.bank import FailingBankClient
from modernized.services.policy.models import PolicyApplication


async def _active_policy(platform, customer_id="CUST-1", coverage=100_000):
    app = PolicyApplication(
        customer_id=customer_id,
        policy_type="auto",
        coverage_amount=coverage,
        start_date=datetime.now() - timedelta(days=1),
        end_date=datetime.now() + timedelta(days=365),
    )
    policy = await platform.policy.create_policy(app, "agent1", "agent")
    await platform.policy.activate_policy(policy.id, "mgr", "manager")
    return policy


def _submission(policy_id, amount=5_000, description="Schade aan de auto na botsing"):
    return ClaimSubmission(
        policy_id=policy_id,
        claim_type=ClaimType.AUTO,
        description=description,
        amount_claimed=amount,
        incident_date=datetime.now() - timedelta(days=2),
    )


class TestSubmitClaim:
    async def test_submit_success(self, platform):
        policy = await _active_policy(platform)
        claim = await platform.claims.submit_claim(
            _submission(policy.id), "CUST-1", "CUST-1"
        )
        assert claim.status == ClaimStatus.SUBMITTED
        assert claim.submitted_at is not None

    async def test_submit_rejects_unowned_policy(self, platform):
        policy = await _active_policy(platform, customer_id="OTHER")
        with pytest.raises(PermissionError, match="not owned"):
            await platform.claims.submit_claim(
                _submission(policy.id), "CUST-1", "CUST-1"
            )

    async def test_submit_rejects_inactive_policy(self, platform):
        app = PolicyApplication(
            customer_id="CUST-1",
            policy_type="auto",
            coverage_amount=100_000,
            start_date=datetime.now() - timedelta(days=1),
            end_date=datetime.now() + timedelta(days=365),
        )
        policy = await platform.policy.create_policy(app, "agent1", "agent")
        with pytest.raises(ValueError, match="not active"):
            await platform.claims.submit_claim(
                _submission(policy.id), "CUST-1", "CUST-1"
            )

    async def test_submit_rejects_amount_over_coverage(self, platform):
        policy = await _active_policy(platform, coverage=1_000)
        with pytest.raises(ValueError, match="exceeds"):
            await platform.claims.submit_claim(
                _submission(policy.id, amount=50_000), "CUST-1", "CUST-1"
            )


class TestDecision:
    async def _reviewable_claim(self, platform, amount=5_000):
        policy = await _active_policy(platform, coverage=1_000_000)
        claim = await platform.claims.submit_claim(
            _submission(policy.id, amount=amount), "CUST-1", "CUST-1"
        )
        await platform.claims.advance_status(
            claim.id, ClaimStatus.VALIDATED, "agent1", "agent"
        )
        await platform.claims.advance_status(
            claim.id, ClaimStatus.UNDER_REVIEW, "agent1", "agent"
        )
        return claim

    async def test_approve_triggers_payment_and_paid(self, platform):
        claim = await self._reviewable_claim(platform)
        await platform.claims.process_decision(
            ClaimDecision(
                claim_id=claim.id, decision="approved",
                approved_amount=5_000, processed_by="agent1",
            ),
            "agent1", "agent",
        )
        updated = await platform.claims.repository.get(claim.id)
        assert updated.status == ClaimStatus.PAID
        assert len(await platform.payments.repository.list_all()) == 1

    async def test_reject_transitions_to_rejected(self, platform):
        claim = await self._reviewable_claim(platform)
        await platform.claims.process_decision(
            ClaimDecision(
                claim_id=claim.id, decision="rejected",
                notes="insufficient evidence", processed_by="agent1",
            ),
            "agent1", "agent",
        )
        updated = await platform.claims.repository.get(claim.id)
        assert updated.status == ClaimStatus.REJECTED

    async def test_four_eyes_blocks_junior_high_value(self, platform):
        claim = await self._reviewable_claim(platform, amount=80_000)
        with pytest.raises(PermissionError, match="senior_agent"):
            await platform.claims.process_decision(
                ClaimDecision(
                    claim_id=claim.id, decision="approved",
                    approved_amount=80_000, processed_by="agent1",
                ),
                "agent1", "agent",
            )

    async def test_segregation_of_duties(self, platform):
        policy = await _active_policy(platform)
        claim = await platform.claims.submit_claim(
            _submission(policy.id), "CUST-1", "CUST-1"
        )
        await platform.claims.advance_status(
            claim.id, ClaimStatus.VALIDATED, "agent1", "agent"
        )
        await platform.claims.advance_status(
            claim.id, ClaimStatus.UNDER_REVIEW, "agent1", "agent"
        )
        with pytest.raises(PermissionError, match="own claim"):
            await platform.claims.process_decision(
                ClaimDecision(
                    claim_id=claim.id, decision="approved",
                    approved_amount=5_000, processed_by="CUST-1",
                ),
                "CUST-1", "customer",
            )

    async def test_decision_missing_claim(self, platform):
        with pytest.raises(ValueError, match="not found"):
            await platform.claims.process_decision(
                ClaimDecision(
                    claim_id="nope", decision="approved",
                    approved_amount=1, processed_by="agent1",
                ),
                "agent1", "agent",
            )

    async def test_advance_denied_for_customer(self, platform):
        policy = await _active_policy(platform)
        claim = await platform.claims.submit_claim(
            _submission(policy.id), "CUST-1", "CUST-1"
        )
        with pytest.raises(PermissionError, match="claims:process"):
            await platform.claims.advance_status(
                claim.id, ClaimStatus.VALIDATED, "CUST-1", "customer"
            )


class TestFraudAndPaymentEvents:
    async def test_high_risk_claim_gets_flagged(self, platform):
        policy = await _active_policy(platform, coverage=1_000_000)
        claim = await platform.claims.submit_claim(
            _submission(
                policy.id, amount=200_000,
                description="gestolen nieuw toestel na brand",
            ),
            "CUST-1", "CUST-1",
        )
        updated = await platform.claims.repository.get(claim.id)
        assert updated.status == ClaimStatus.FLAGGED
        assert updated.fraud_score is not None
        assert platform.events.get_dead_letters() == []

    async def test_payment_failure_does_not_mark_paid(self):
        platform = build_platform(bank_client=FailingBankClient())
        policy = await _active_policy(platform, coverage=1_000_000)
        claim = await platform.claims.submit_claim(
            _submission(policy.id), "CUST-1", "CUST-1"
        )
        await platform.claims.advance_status(
            claim.id, ClaimStatus.VALIDATED, "agent1", "agent"
        )
        await platform.claims.advance_status(
            claim.id, ClaimStatus.UNDER_REVIEW, "agent1", "agent"
        )
        await platform.claims.process_decision(
            ClaimDecision(
                claim_id=claim.id, decision="approved",
                approved_amount=5_000, processed_by="agent1",
            ),
            "agent1", "agent",
        )
        updated = await platform.claims.repository.get(claim.id)
        assert updated.status == ClaimStatus.APPROVED

    async def test_mark_paid_missing_claim(self, platform):
        with pytest.raises(ValueError, match="not found"):
            await platform.claims.mark_paid("nope")

    async def test_flag_missing_claim(self, platform):
        with pytest.raises(ValueError, match="not found"):
            await platform.claims.flag_claim("nope", "r", 0.9, "system")

    async def test_audit_chain_intact_after_flow(self, platform):
        await self._run_happy_path(platform)
        ok, bad = platform.audit.verify_integrity()
        assert ok is True
        assert bad is None

    async def _run_happy_path(self, platform):
        policy = await _active_policy(platform, coverage=1_000_000)
        claim = await platform.claims.submit_claim(
            _submission(policy.id), "CUST-1", "CUST-1"
        )
        await platform.claims.advance_status(
            claim.id, ClaimStatus.VALIDATED, "agent1", "agent"
        )
        await platform.claims.advance_status(
            claim.id, ClaimStatus.UNDER_REVIEW, "agent1", "agent"
        )
        await platform.claims.process_decision(
            ClaimDecision(
                claim_id=claim.id, decision="approved",
                approved_amount=5_000, processed_by="agent1",
            ),
            "agent1", "agent",
        )
