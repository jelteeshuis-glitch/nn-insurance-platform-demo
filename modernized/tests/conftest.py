"""Shared pytest fixtures for the modernized service test suite."""
from datetime import datetime, timedelta

import pytest

from governance.audit import AuditLogger
from modernized.platform import build_platform
from modernized.services.claims.models import ClaimSubmission, ClaimType
from modernized.services.policy.models import PolicyApplication
from modernized.shared.events import EventBus


@pytest.fixture
def audit() -> AuditLogger:
    return AuditLogger()


@pytest.fixture
def events() -> EventBus:
    return EventBus(service_name="test")


@pytest.fixture
def platform():
    """A fully-wired in-process platform (all five contexts + event bus)."""
    return build_platform()


@pytest.fixture
def policy_application() -> PolicyApplication:
    return PolicyApplication(
        customer_id="CUST-001",
        policy_type="auto",
        coverage_amount=100_000,
        start_date=datetime.now() - timedelta(days=1),
        end_date=datetime.now() + timedelta(days=365),
    )


@pytest.fixture
def claim_submission() -> ClaimSubmission:
    return ClaimSubmission(
        policy_id="POL-001",
        claim_type=ClaimType.AUTO,
        description="Schade aan voertuig door aanrijding op A2",
        amount_claimed=5_000.00,
        incident_date=datetime.now() - timedelta(days=1),
    )
