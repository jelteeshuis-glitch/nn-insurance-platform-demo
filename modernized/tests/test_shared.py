"""
Tests for shared infrastructure: repository, encryption, event bus,
notifications, auth (RBAC/rate-limit/lockout), HTTP helpers, and fraud service.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from governance.audit import AuditLogger
from modernized.services.fraud.service import FraudDetectionService
from modernized.shared.auth import (
    AccountLockout,
    AuthContext,
    RateLimiter,
    Role,
    authorize,
    require_permission,
    role_has_permission,
)
from modernized.shared.encryption import FernetEncryptionService
from modernized.shared.events import DomainEvent, EventBus
from modernized.shared.http import Actor, get_actor, register_exception_handlers
from modernized.shared.notifications import NotificationService
from modernized.shared.repository import InMemoryRepository


@dataclass
class _Item:
    id: str
    value: int = 0


# ============================================================
# Repository
# ============================================================

class TestRepository:
    async def test_crud_lifecycle(self):
        repo = InMemoryRepository[_Item]()
        item = _Item(id="a", value=1)
        await repo.save(item)
        assert await repo.exists("a")
        assert (await repo.get("a")).value == 1
        assert await repo.list_all() == [item]
        assert await repo.delete("a") is True
        assert await repo.delete("a") is False
        assert await repo.get("a") is None

    async def test_custom_id_getter_and_find(self):
        repo = InMemoryRepository[_Item](id_getter=lambda e: e.id)
        await repo.save(_Item(id="a", value=1))
        await repo.save(_Item(id="b", value=2))
        found = await repo.find(lambda e: e.value > 1)
        assert len(found) == 1
        assert found[0].id == "b"


# ============================================================
# Encryption
# ============================================================

class TestEncryption:
    def test_round_trip(self):
        svc = FernetEncryptionService()
        token = svc.encrypt("secret-bsn")
        assert token != "secret-bsn"
        assert svc.decrypt(token) == "secret-bsn"

    def test_accepts_provided_key_as_str(self):
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        svc = FernetEncryptionService(key=key)
        assert svc.decrypt(svc.encrypt("x")) == "x"


# ============================================================
# Event Bus
# ============================================================

class TestEventBus:
    async def test_publish_to_multiple_handlers(self):
        bus = EventBus("test")
        received = []

        async def h1(e):
            received.append(("h1", e))

        async def h2(e):
            received.append(("h2", e))

        bus.subscribe("thing.happened", h1)
        bus.subscribe("thing.happened", h2)
        event = await bus.publish("thing.happened", {"x": 1}, correlation_id="corr")
        assert len(received) == 2
        assert event.correlation_id == "corr"

    async def test_failing_handler_goes_to_dead_letter(self):
        bus = EventBus("test")

        async def boom(e):
            raise RuntimeError("nope")

        bus.subscribe("thing.happened", boom)
        await bus.publish("thing.happened", {})
        dead = bus.get_dead_letters()
        assert len(dead) == 1
        assert dead[0].metadata["failed_handler"] == "boom"

    def test_domain_event_to_json(self):
        event = DomainEvent(event_type="x", payload={"a": 1})
        assert '"event_type": "x"' in event.to_json()


# ============================================================
# Notifications
# ============================================================

class TestNotifications:
    async def test_masks_pii(self):
        svc = NotificationService()
        await svc.handle_event(DomainEvent(
            event_type="claim.submitted",
            payload={"email": "jan@example.nl", "iban": "NL91ABNA0417164300"},
        ))
        note = svc.notifications_for("claim.submitted")[0]
        assert "jan@example.nl" not in note.message
        assert "NL91ABNA0417164300" not in note.message


# ============================================================
# Auth
# ============================================================

class TestAuth:
    def test_role_has_permission(self):
        assert role_has_permission(Role.MANAGER, "payments:refund")
        assert not role_has_permission(Role.CUSTOMER, "payments:refund")
        assert not role_has_permission("bogus", "payments:refund")

    def test_authorize_raises(self):
        with pytest.raises(PermissionError):
            authorize("customer", "payments:refund")
        authorize("manager", "payments:refund")  # no raise

    def test_auth_context_helpers(self):
        now = datetime.now(timezone.utc)
        ctx = AuthContext(
            user_id="u", username="u", role=Role.SENIOR_AGENT,
            permissions={"claims:process"}, session_id="s",
            authenticated_at=now, expires_at=now + timedelta(hours=1),
        )
        assert not ctx.is_expired
        assert ctx.has_permission("claims:process")
        assert ctx.can_approve_amount(80_000)
        assert ctx.can_approve_amount(1_000)

    def test_auth_context_cannot_approve_high(self):
        now = datetime.now(timezone.utc)
        ctx = AuthContext(
            user_id="u", username="u", role=Role.AGENT,
            permissions={"claims:process"}, session_id="s",
            authenticated_at=now, expires_at=now + timedelta(hours=1),
        )
        assert not ctx.can_approve_amount(80_000)

    def test_rate_limiter(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        assert limiter.is_allowed("u")
        assert limiter.is_allowed("u")
        assert not limiter.is_allowed("u")

    def test_account_lockout(self):
        lockout = AccountLockout(max_attempts=3, lockout_minutes=30)
        for _ in range(3):
            lockout.record_failure("u")
        assert lockout.is_locked("u")
        lockout.clear("u")
        assert not lockout.is_locked("u")

    def test_account_lockout_not_locked_initially(self):
        assert not AccountLockout().is_locked("fresh")

    async def test_require_permission_decorator(self):
        now = datetime.now(timezone.utc)

        class Svc:
            @require_permission("claims:process")
            async def do(self, *, auth_context):
                return "ok"

        svc = Svc()
        good = AuthContext(
            user_id="u", username="u", role=Role.AGENT,
            permissions={"claims:process"}, session_id="s",
            authenticated_at=now, expires_at=now + timedelta(hours=1),
        )
        assert await svc.do(auth_context=good) == "ok"

        expired = AuthContext(
            user_id="u", username="u", role=Role.AGENT,
            permissions={"claims:process"}, session_id="s",
            authenticated_at=now, expires_at=now - timedelta(hours=1),
        )
        with pytest.raises(PermissionError, match="expired"):
            await svc.do(auth_context=expired)

        denied = AuthContext(
            user_id="u", username="u", role=Role.AGENT,
            permissions=set(), session_id="s",
            authenticated_at=now, expires_at=now + timedelta(hours=1),
        )
        with pytest.raises(PermissionError, match="Permission denied"):
            await svc.do(auth_context=denied)


# ============================================================
# HTTP helpers
# ============================================================

class TestHttp:
    def test_get_actor_defaults(self):
        class Req:
            headers = {}

        actor = get_actor(Req())
        assert actor == Actor(actor="anonymous", role="customer")

    def test_get_actor_from_headers(self):
        class Req:
            headers = {"X-Actor": "mgr", "X-Actor-Role": "manager"}

        actor = get_actor(Req())
        assert actor.actor == "mgr"
        assert actor.role == "manager"

    def test_register_exception_handlers(self):
        from fastapi import FastAPI
        app = FastAPI()
        register_exception_handlers(app)
        assert PermissionError in app.exception_handlers
        assert ValueError in app.exception_handlers


# ============================================================
# Fraud service
# ============================================================

class TestFraud:
    def test_low_risk_not_flagged(self):
        svc = FraudDetectionService(AuditLogger(), EventBus("fraud"))
        assessment = svc.assess("c1", 1_000, "normal claim")
        assert not assessment.flagged
        assert assessment.score == 0.0

    def test_high_risk_flagged(self):
        svc = FraudDetectionService(AuditLogger(), EventBus("fraud"))
        assessment = svc.assess("c1", 200_000, "gestolen nieuw na brand")
        assert assessment.flagged
        assert assessment.score >= 0.7
        assert "high_amount" in assessment.contributions

    async def test_on_claim_submitted_flags_and_audits(self):
        bus = EventBus("fraud")
        flagged = []

        async def handler(e):
            flagged.append(e)

        bus.subscribe("fraud.flagged", handler)
        audit = AuditLogger()
        svc = FraudDetectionService(audit, bus)
        await svc.on_claim_submitted(DomainEvent(
            event_type="claim.submitted",
            payload={"claim_id": "c1", "amount": 200_000,
                     "description": "gestolen nieuw na brand"},
        ))
        assert len(flagged) == 1
        assert len(audit.query()) == 1

    async def test_on_claim_submitted_low_risk_no_flag(self):
        bus = EventBus("fraud")
        flagged = []

        async def handler(e):
            flagged.append(e)

        bus.subscribe("fraud.flagged", handler)
        svc = FraudDetectionService(AuditLogger(), bus)
        await svc.on_claim_submitted(DomainEvent(
            event_type="claim.submitted",
            payload={"claim_id": "c1", "amount": 100, "description": "ok"},
        ))
        assert flagged == []
