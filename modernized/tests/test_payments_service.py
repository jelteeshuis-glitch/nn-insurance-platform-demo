"""
Payment Service Tests — mirrors test_claims_service.py.

Covers IBAN validation/tokenization, the payment state machine, idempotency,
circuit-breaker behaviour, bank failures, refunds, authorization, and the
``claim.approved`` event consumer.
"""
import pytest

from governance.audit import AuditLogger
from modernized.services.payments.bank import FailingBankClient, SimulatedBankClient
from modernized.services.payments.models import (
    Payment,
    PaymentInstruction,
    PaymentStatus,
    RefundRequest,
    tokenize_iban,
    validate_iban,
)
from modernized.services.payments.repository import PaymentRepository
from modernized.services.payments.service import CircuitBreaker, PaymentService
from modernized.shared.events import DomainEvent, EventBus

VALID_IBAN = "NL91ABNA0417164300"


def _service(bank=None):
    return PaymentService(
        repository=PaymentRepository(),
        bank_client=bank or SimulatedBankClient(),
        audit_logger=AuditLogger(),
        event_bus=EventBus("payments"),
    )


def _instruction(**overrides) -> PaymentInstruction:
    data = dict(claim_id="CLM-1", amount=5_000, iban=VALID_IBAN)
    data.update(overrides)
    return PaymentInstruction(**data)


# ============================================================
# IBAN + Model Validation
# ============================================================

class TestIbanAndModels:
    def test_valid_iban(self):
        assert validate_iban(VALID_IBAN)
        assert validate_iban("NL91 ABNA 0417 1643 00")

    def test_invalid_iban_checksum(self):
        assert not validate_iban("NL00ABNA0417164300")

    def test_invalid_iban_too_short(self):
        assert not validate_iban("NL91")

    def test_invalid_iban_bad_chars(self):
        assert not validate_iban("NL91ABNA04171643$$")

    def test_tokenize_is_stable_and_opaque(self):
        token = tokenize_iban(VALID_IBAN)
        assert token.startswith("tok_")
        assert VALID_IBAN not in token
        assert token == tokenize_iban(VALID_IBAN)

    def test_instruction_rejects_bad_iban(self):
        with pytest.raises(ValueError, match="Invalid IBAN"):
            _instruction(iban="NL00ABNA0417164300")

    def test_instruction_to_payment_tokenizes(self):
        payment = _instruction().to_payment()
        assert payment.iban_token.startswith("tok_")
        assert payment.status == PaymentStatus.PENDING

    def test_amount_rounded(self):
        assert _instruction(amount=10.129).amount == 10.13

    def test_payment_state_machine_invalid(self):
        payment = Payment(claim_id="C", amount=10)
        with pytest.raises(ValueError, match="Invalid transition"):
            payment.transition_to(PaymentStatus.REFUNDED)


class TestCircuitBreaker:
    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=2)
        assert cb.is_available()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        assert not cb.is_available()

    def test_recovers_on_success(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        cb.record_success()
        assert cb.state == "closed"
        assert cb.is_available()


# ============================================================
# Service Layer
# ============================================================

class TestPaymentService:
    async def test_process_payment_success(self):
        svc = _service()
        payment = await svc.process_payment(_instruction(), "mgr", "manager")
        assert payment.status == PaymentStatus.COMPLETED
        assert payment.bank_reference is not None

    async def test_process_payment_denied(self):
        svc = _service()
        with pytest.raises(PermissionError, match="payments:initiate"):
            await svc.process_payment(_instruction(), "cust", "customer")

    async def test_idempotency_returns_existing(self):
        svc = _service()
        instr = _instruction(idempotency_key="key-1")
        first = await svc.process_payment(instr, "mgr", "manager")
        second = await svc.process_payment(
            _instruction(idempotency_key="key-1"), "mgr", "manager"
        )
        assert first.id == second.id
        assert len(await svc.repository.list_all()) == 1

    async def test_bank_failure_marks_failed(self):
        svc = _service(bank=FailingBankClient())
        payment = await svc.process_payment(_instruction(), "mgr", "manager")
        assert payment.status == PaymentStatus.FAILED
        assert payment.error
        assert svc.circuit_breaker.failures == 1

    async def test_circuit_open_fails_fast(self):
        svc = _service()
        svc.circuit_breaker.state = "open"
        svc.circuit_breaker.last_failure = None
        payment = await svc.process_payment(_instruction(), "mgr", "manager")
        assert payment.status == PaymentStatus.FAILED
        assert "circuit open" in payment.error

    async def test_publishes_completed_event(self):
        svc = _service()
        received = []

        async def handler(event):
            received.append(event)

        svc.events.subscribe("payment.completed", handler)
        await svc.process_payment(_instruction(), "mgr", "manager")
        assert len(received) == 1

    async def test_refund_success(self):
        svc = _service()
        payment = await svc.process_payment(_instruction(), "mgr", "manager")
        refunded = await svc.process_refund(
            RefundRequest(payment_id=payment.id, reason="duplicate"),
            "mgr", "manager",
        )
        assert refunded.status == PaymentStatus.REFUNDED
        assert refunded.refunded_amount == payment.amount

    async def test_refund_partial(self):
        svc = _service()
        payment = await svc.process_payment(_instruction(amount=1000), "mgr", "manager")
        refunded = await svc.process_refund(
            RefundRequest(payment_id=payment.id, reason="partial", amount=400),
            "mgr", "manager",
        )
        assert refunded.refunded_amount == 400

    async def test_refund_denied_for_agent(self):
        svc = _service()
        payment = await svc.process_payment(_instruction(), "mgr", "manager")
        with pytest.raises(PermissionError, match="payments:refund"):
            await svc.process_refund(
                RefundRequest(payment_id=payment.id, reason="err"), "a", "agent"
            )

    async def test_refund_missing_payment(self):
        svc = _service()
        with pytest.raises(ValueError, match="not found"):
            await svc.process_refund(
                RefundRequest(payment_id="nope", reason="err"), "mgr", "manager"
            )

    async def test_refund_uncompleted_payment(self):
        svc = _service(bank=FailingBankClient())
        payment = await svc.process_payment(_instruction(), "mgr", "manager")
        with pytest.raises(ValueError, match="completed payments"):
            await svc.process_refund(
                RefundRequest(payment_id=payment.id, reason="err"), "mgr", "manager"
            )

    async def test_refund_exceeds_original(self):
        svc = _service()
        payment = await svc.process_payment(_instruction(amount=100), "mgr", "manager")
        with pytest.raises(ValueError, match="exceeds original"):
            await svc.process_refund(
                RefundRequest(payment_id=payment.id, reason="err", amount=999),
                "mgr", "manager",
            )

    async def test_on_claim_approved_creates_payment(self):
        svc = _service()
        event = DomainEvent(
            event_type="claim.approved",
            payload={"claim_id": "CLM-9", "customer_id": "C1", "amount_approved": 2500},
        )
        await svc.on_claim_approved(event)
        payments = await svc.repository.list_all()
        assert len(payments) == 1
        assert payments[0].status == PaymentStatus.COMPLETED

    async def test_on_claim_approved_ignores_zero_amount(self):
        svc = _service()
        event = DomainEvent(
            event_type="claim.approved",
            payload={"claim_id": "CLM-9", "amount_approved": None},
        )
        await svc.on_claim_approved(event)
        assert len(await svc.repository.list_all()) == 0

    async def test_on_claim_approved_uses_account_resolver(self):
        async def resolver(customer_id):
            return VALID_IBAN

        svc = PaymentService(
            repository=PaymentRepository(),
            bank_client=SimulatedBankClient(),
            audit_logger=AuditLogger(),
            event_bus=EventBus("payments"),
            account_resolver=resolver,
        )
        event = DomainEvent(
            event_type="claim.approved",
            payload={"claim_id": "CLM-1", "customer_id": "C1", "amount_approved": 100},
        )
        await svc.on_claim_approved(event)
        assert len(await svc.repository.list_all()) == 1
