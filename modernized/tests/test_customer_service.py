"""
Customer Service Tests — mirrors test_claims_service.py.

Covers BSN/email validation, PII encryption at rest, purpose-logged access,
consent management, right-to-erasure (incl. legal-hold blocking), data
portability, and authorization.
"""
import pytest

from governance.audit import AuditEventType, AuditLogger
from modernized.services.customer.models import (
    ConsentType,
    ConsentUpdate,
    Customer,
    CustomerRegistration,
    validate_bsn,
)
from modernized.services.customer.service import CustomerService
from modernized.shared.encryption import FernetEncryptionService
from modernized.shared.repository import InMemoryRepository

# A BSN that passes the 11-proef checksum.
VALID_BSN = "111222333"


def _service(active_claims_lookup=None):
    return CustomerService(
        repository=InMemoryRepository[Customer](),
        encryption_service=FernetEncryptionService(),
        audit_logger=AuditLogger(),
        active_claims_lookup=active_claims_lookup,
    )


def _registration(**overrides) -> CustomerRegistration:
    data = dict(
        bsn=VALID_BSN,
        first_name="Jan",
        last_name="de Vries",
        email="jan@example.nl",
        phone="+31612345678",
        address="Damstraat 1, Amsterdam",
    )
    data.update(overrides)
    return CustomerRegistration(**data)


# ============================================================
# Validation
# ============================================================

class TestValidation:
    def test_valid_bsn(self):
        assert validate_bsn(VALID_BSN)

    def test_invalid_bsn_checksum(self):
        assert not validate_bsn("123456789")

    def test_invalid_bsn_length(self):
        assert not validate_bsn("12345")

    def test_registration_rejects_bad_bsn(self):
        with pytest.raises(ValueError, match="Invalid BSN"):
            _registration(bsn="123456789")

    def test_registration_rejects_bad_email(self):
        with pytest.raises(ValueError, match="Invalid email"):
            _registration(email="not-an-email")


# ============================================================
# Service Layer
# ============================================================

class TestCustomerService:
    async def test_register_encrypts_pii(self):
        svc = _service()
        customer = await svc.register_customer(_registration(), "agent1", "agent")
        assert customer.bsn_encrypted != VALID_BSN
        assert svc.encryption.decrypt(customer.bsn_encrypted) == VALID_BSN
        assert customer.has_consent(ConsentType.ESSENTIAL)

    async def test_register_denied_for_customer_role(self):
        svc = _service()
        with pytest.raises(PermissionError, match="customer:register"):
            await svc.register_customer(_registration(), "cust", "customer")

    async def test_get_customer_logs_access(self):
        svc = _service()
        customer = await svc.register_customer(_registration(), "agent1", "agent")
        fetched = await svc.get_customer(customer.id, "servicing", "agent1", "agent")
        assert fetched is not None
        reads = svc.audit.query(event_type=AuditEventType.DATA_READ)
        assert len(reads) == 1
        assert reads[0].justification == "servicing"

    async def test_get_customer_not_found(self):
        svc = _service()
        assert await svc.get_customer("nope", "x", "agent1", "agent") is None

    async def test_get_customer_denied(self):
        svc = _service()
        customer = await svc.register_customer(_registration(), "agent1", "agent")
        with pytest.raises(PermissionError, match="customer:read"):
            await svc.get_customer(customer.id, "x", "cust", "customer")

    async def test_update_consent_new_and_withdraw(self):
        svc = _service()
        customer = await svc.register_customer(_registration(), "agent1", "agent")
        await svc.update_consent(
            customer.id,
            ConsentUpdate(consent_type=ConsentType.MARKETING, granted=True),
            customer.id, "customer",
        )
        updated = await svc.repository.get(customer.id)
        assert updated.has_consent(ConsentType.MARKETING)
        await svc.update_consent(
            customer.id,
            ConsentUpdate(consent_type=ConsentType.MARKETING, granted=False),
            customer.id, "customer",
        )
        updated = await svc.repository.get(customer.id)
        assert not updated.has_consent(ConsentType.MARKETING)

    async def test_update_consent_missing_customer(self):
        svc = _service()
        with pytest.raises(ValueError, match="not found"):
            await svc.update_consent(
                "nope",
                ConsentUpdate(consent_type=ConsentType.MARKETING, granted=True),
                "a", "agent",
            )

    async def test_right_to_erasure_success(self):
        svc = _service()
        customer = await svc.register_customer(_registration(), "agent1", "agent")
        result = await svc.right_to_erasure(customer.id, "mgr", "manager")
        assert result["success"] is True
        erased = await svc.repository.get(customer.id)
        assert erased.first_name == "[ERASED]"
        assert erased.is_deleted is True
        # Erased customers are invisible to normal reads.
        assert await svc.get_customer(customer.id, "x", "agent1", "agent") is None

    async def test_right_to_erasure_blocked_by_active_claims(self):
        async def lookup(customer_id):
            return ["CLM-1"]

        svc = _service(active_claims_lookup=lookup)
        customer = await svc.register_customer(_registration(), "agent1", "agent")
        result = await svc.right_to_erasure(customer.id, "mgr", "manager")
        assert result["success"] is False
        assert result["blocked_by"] == ["CLM-1"]

    async def test_right_to_erasure_not_found(self):
        svc = _service()
        result = await svc.right_to_erasure("nope", "mgr", "manager")
        assert result["success"] is False

    async def test_right_to_erasure_denied_for_agent(self):
        svc = _service()
        customer = await svc.register_customer(_registration(), "agent1", "agent")
        with pytest.raises(PermissionError, match="customer:erase"):
            await svc.right_to_erasure(customer.id, "agent1", "agent")

    async def test_data_portability_success(self):
        svc = _service()
        customer = await svc.register_customer(_registration(), "agent1", "agent")
        export = await svc.data_portability(customer.id, customer.id, "customer")
        assert export["success"] is True
        assert export["data"]["personal_info"]["email"] == "jan@example.nl"

    async def test_data_portability_not_found(self):
        svc = _service()
        export = await svc.data_portability("nope", "mgr", "manager")
        assert export["success"] is False
