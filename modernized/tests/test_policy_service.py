"""
Policy Service Tests — mirrors test_claims_service.py.

Covers input validation, the policy state machine, premium calculation,
authorization, coverage verification, and audit/event side effects.
"""
from datetime import datetime, timedelta

import pytest

from governance.audit import AuditLogger
from modernized.services.policy.models import (
    BASE_PREMIUM_RATE,
    Policy,
    PolicyApplication,
    PolicyStatus,
    PolicyType,
    calculate_premium,
)
from modernized.services.policy.service import PolicyService
from modernized.shared.events import EventBus
from modernized.shared.repository import InMemoryRepository


def _service():
    return PolicyService(
        repository=InMemoryRepository[Policy](),
        audit_logger=AuditLogger(),
        event_bus=EventBus("policy"),
    )


def _application(**overrides) -> PolicyApplication:
    data = dict(
        customer_id="CUST-001",
        policy_type=PolicyType.AUTO,
        coverage_amount=100_000,
        start_date=datetime.now() - timedelta(days=1),
        end_date=datetime.now() + timedelta(days=365),
    )
    data.update(overrides)
    return PolicyApplication(**data)


# ============================================================
# Model Validation
# ============================================================

class TestPolicyApplicationValidation:
    def test_valid_application(self):
        app = _application()
        assert app.coverage_amount == 100_000

    def test_rejects_zero_coverage(self):
        with pytest.raises(ValueError, match="greater than 0"):
            _application(coverage_amount=0)

    def test_rejects_coverage_above_max(self):
        with pytest.raises(ValueError, match="less than or equal to"):
            _application(coverage_amount=10**9)

    def test_rejects_end_before_start(self):
        with pytest.raises(ValueError, match="end_date must be after"):
            _application(
                start_date=datetime.now(),
                end_date=datetime.now() - timedelta(days=1),
            )

    def test_coverage_rounded(self):
        app = _application(coverage_amount=1234.567)
        assert app.coverage_amount == 1234.57


class TestPremiumCalculation:
    def test_premium_includes_tax(self):
        premium = calculate_premium(PolicyType.AUTO, 100_000)
        expected = round(100_000 * BASE_PREMIUM_RATE[PolicyType.AUTO] * 1.21, 2)
        assert premium == expected

    @pytest.mark.parametrize("ptype", list(PolicyType))
    def test_premium_positive_for_all_types(self, ptype):
        assert calculate_premium(ptype, 50_000) > 0


# ============================================================
# State Machine
# ============================================================

class TestPolicyStateMachine:
    def _policy(self, status: PolicyStatus) -> Policy:
        return Policy(
            customer_id="CUST-001",
            policy_type=PolicyType.AUTO,
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=365),
            premium_amount=100,
            coverage_amount=100_000,
            status=status,
        )

    def test_draft_to_active(self):
        policy = self._policy(PolicyStatus.DRAFT)
        policy.transition_to(PolicyStatus.ACTIVE)
        assert policy.status == PolicyStatus.ACTIVE

    def test_cancelled_is_terminal(self):
        policy = self._policy(PolicyStatus.CANCELLED)
        with pytest.raises(ValueError, match="Invalid transition"):
            policy.transition_to(PolicyStatus.ACTIVE)

    def test_invalid_draft_to_expired(self):
        policy = self._policy(PolicyStatus.DRAFT)
        with pytest.raises(ValueError, match="Invalid transition"):
            policy.transition_to(PolicyStatus.EXPIRED)

    @pytest.mark.parametrize("frm,to", [
        (PolicyStatus.ACTIVE, PolicyStatus.SUSPENDED),
        (PolicyStatus.SUSPENDED, PolicyStatus.ACTIVE),
        (PolicyStatus.ACTIVE, PolicyStatus.EXPIRED),
        (PolicyStatus.EXPIRED, PolicyStatus.RENEWED),
    ])
    def test_valid_transitions(self, frm, to):
        policy = self._policy(frm)
        policy.transition_to(to)
        assert policy.status == to


# ============================================================
# Service Layer
# ============================================================

class TestPolicyService:
    async def test_create_policy_success(self):
        svc = _service()
        policy = await svc.create_policy(_application(), "agent1", "agent")
        assert policy.status == PolicyStatus.DRAFT
        assert policy.premium_amount > 0
        stored = await svc.get_policy(policy.id)
        assert stored is not None

    async def test_create_policy_denied_for_customer(self):
        svc = _service()
        with pytest.raises(PermissionError, match="policy:create"):
            await svc.create_policy(_application(), "cust1", "customer")

    async def test_create_publishes_event_and_audits(self):
        svc = _service()
        seen = []

        async def handler(event):
            seen.append(event)

        svc.events.subscribe("policy.created", handler)
        await svc.create_policy(_application(), "agent1", "agent")
        assert len(seen) == 1
        assert len(svc.audit.query()) == 1

    async def test_activate_suspend_cancel_flow(self):
        svc = _service()
        policy = await svc.create_policy(_application(), "agent1", "agent")
        await svc.activate_policy(policy.id, "mgr", "manager")
        assert (await svc.get_policy(policy.id)).status == PolicyStatus.ACTIVE
        await svc.suspend_policy(policy.id, "non-payment", "mgr", "manager")
        assert (await svc.get_policy(policy.id)).status == PolicyStatus.SUSPENDED
        await svc.activate_policy(policy.id, "mgr", "manager")
        await svc.cancel_policy(policy.id, "customer request", "mgr", "manager")
        assert (await svc.get_policy(policy.id)).status == PolicyStatus.CANCELLED

    async def test_manage_denied_for_agent(self):
        svc = _service()
        policy = await svc.create_policy(_application(), "agent1", "agent")
        with pytest.raises(PermissionError, match="policy:manage"):
            await svc.activate_policy(policy.id, "agent1", "agent")

    async def test_activate_missing_policy(self):
        svc = _service()
        with pytest.raises(ValueError, match="not found"):
            await svc.activate_policy("nope", "mgr", "manager")

    async def test_verify_coverage_active(self):
        svc = _service()
        policy = await svc.create_policy(_application(), "agent1", "agent")
        await svc.activate_policy(policy.id, "mgr", "manager")
        result = await svc.verify_coverage(policy.id, 40_000)
        assert result.covered is True
        assert result.remaining_coverage == 60_000

    async def test_verify_coverage_exceeds(self):
        svc = _service()
        policy = await svc.create_policy(_application(), "agent1", "agent")
        await svc.activate_policy(policy.id, "mgr", "manager")
        result = await svc.verify_coverage(policy.id, 200_000)
        assert result.covered is False
        assert "exceeds" in result.reason

    async def test_verify_coverage_not_found(self):
        svc = _service()
        result = await svc.verify_coverage("missing", 100)
        assert result.covered is False
        assert result.reason == "Policy not found"

    async def test_verify_coverage_not_active(self):
        svc = _service()
        policy = await svc.create_policy(_application(), "agent1", "agent")
        result = await svc.verify_coverage(policy.id, 100)
        assert result.covered is False
        assert "draft" in result.reason
