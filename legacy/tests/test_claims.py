"""
Test suite for claims processing — ~45% coverage.
Missing: integration tests, edge cases, security tests, performance tests.
"""
import pytest

from legacy.src.database import Database
from legacy.src.claims import ClaimsProcessor


@pytest.fixture
def db():
    """Create test database."""
    database = Database(":memory:")
    database.connect()
    # Seed test data
    cursor = database.connection.cursor()
    cursor.execute("""
        INSERT INTO customers (id, bsn, first_name, last_name, email)
        VALUES (1, '123456789', 'Jan', 'de Vries', 'jan@test.nl')
    """)
    cursor.execute("""
        INSERT INTO policies (id, customer_id, policy_number, policy_type, coverage_amount, status)
        VALUES (1, 1, 'POL-2024-001', 'auto', 50000, 'active')
    """)
    database.connection.commit()
    return database


@pytest.fixture
def processor(db):
    """Create claims processor."""
    return ClaimsProcessor(db)


class TestClaimSubmission:
    """Basic submission tests — no edge cases covered."""

    def test_submit_valid_claim(self, processor):
        """Test basic claim submission."""
        result = processor.submit_claim(
            customer_id=1,
            policy_id=1,
            claim_type="auto",
            description="Schade aan voertuig door aanrijding",
            amount=5000.00,
        )
        assert result["success"] is True
        assert result["claim_number"] is not None

    def test_submit_claim_exceeds_maximum(self, processor):
        """Test that claims above maximum are rejected."""
        result = processor.submit_claim(
            customer_id=1,
            policy_id=1,
            claim_type="auto",
            description="Totaal verlies",
            amount=2000000.00,
        )
        assert result["success"] is False

    # MISSING TESTS:
    # - test_submit_claim_inactive_policy
    # - test_submit_claim_wrong_customer
    # - test_submit_claim_negative_amount
    # - test_submit_claim_empty_description
    # - test_submit_claim_invalid_type
    # - test_submit_claim_duplicate
    # - test_submit_claim_concurrent_submissions
    # - test_fraud_detection_high_amount
    # - test_fraud_detection_multiple_claims
    # - test_fraud_detection_suspicious_keywords


class TestClaimProcessing:
    """Minimal processing tests."""

    def test_approve_claim(self, processor, db):
        """Test claim approval — happy path only."""
        # Submit first
        result = processor.submit_claim(
            customer_id=1, policy_id=1, claim_type="auto",
            description="Test", amount=1000.00,
        )
        # Approve
        # NOTE: This test doesn't actually work properly because claim_number != claim_id
        # But it was never caught because it's rarely run

    # MISSING TESTS:
    # - test_reject_claim
    # - test_process_already_processed_claim
    # - test_approve_above_threshold_requires_dual_approval
    # - test_process_flagged_claim
    # - test_unauthorized_user_cannot_approve
    # - test_payment_initiated_after_approval
    # - test_notification_sent_on_decision
