"""
API-layer tests (FastAPI) for all four services using TestClient.

Verifies routing, request/response translation, header-based auth, and the
domain-exception → HTTP status mapping.
"""
import asyncio
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from modernized.platform import build_platform
from modernized.services.claims.api import create_app as claims_app
from modernized.services.customer.api import create_app as customer_app
from modernized.services.payments.api import create_app as payments_app
from modernized.services.policy.api import create_app as policy_app

AGENT = {"X-Actor": "agent1", "X-Actor-Role": "agent"}
MANAGER = {"X-Actor": "mgr", "X-Actor-Role": "manager"}
CUSTOMER = {"X-Actor": "CUST-1", "X-Actor-Role": "customer"}
VALID_IBAN = "NL91ABNA0417164300"
VALID_BSN = "111222333"


def _iso(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat()


# ============================================================
# Policy API
# ============================================================

class TestPolicyApi:
    def test_health(self):
        client = TestClient(policy_app(build_platform().policy))
        assert client.get("/health").json()["service"] == "policy"

    def test_create_and_get(self):
        client = TestClient(policy_app(build_platform().policy))
        resp = client.post("/policies", headers=AGENT, json={
            "customer_id": "CUST-1", "policy_type": "auto",
            "coverage_amount": 100000,
            "start_date": _iso(-1), "end_date": _iso(365),
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]
        assert client.get(f"/policies/{pid}").status_code == 200

    def test_create_denied_returns_403(self):
        client = TestClient(policy_app(build_platform().policy))
        resp = client.post("/policies", headers=CUSTOMER, json={
            "customer_id": "CUST-1", "policy_type": "auto",
            "coverage_amount": 100000,
            "start_date": _iso(-1), "end_date": _iso(365),
        })
        assert resp.status_code == 403

    def test_get_missing_returns_404(self):
        client = TestClient(policy_app(build_platform().policy))
        assert client.get("/policies/nope").status_code == 404

    def test_invalid_body_returns_422(self):
        client = TestClient(policy_app(build_platform().policy))
        resp = client.post("/policies", headers=AGENT, json={
            "customer_id": "CUST-1", "policy_type": "auto",
            "coverage_amount": -5,
            "start_date": _iso(-1), "end_date": _iso(365),
        })
        assert resp.status_code == 422


# ============================================================
# Payments API
# ============================================================

class TestPaymentsApi:
    def test_process_and_refund(self):
        client = TestClient(payments_app(build_platform().payments))
        resp = client.post("/payments", headers=MANAGER, json={
            "claim_id": "CLM-1", "amount": 5000, "iban": VALID_IBAN,
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]
        assert resp.json()["status"] == "completed"
        refund = client.post("/payments/refund", headers=MANAGER, json={
            "payment_id": pid, "reason": "duplicate",
        })
        assert refund.status_code == 200
        assert refund.json()["status"] == "refunded"

    def test_bad_iban_returns_422(self):
        client = TestClient(payments_app(build_platform().payments))
        resp = client.post("/payments", headers=MANAGER, json={
            "claim_id": "CLM-1", "amount": 5000, "iban": "NL00ABNA0417164300",
        })
        assert resp.status_code == 422

    def test_denied_returns_403(self):
        client = TestClient(payments_app(build_platform().payments))
        resp = client.post("/payments", headers=CUSTOMER, json={
            "claim_id": "CLM-1", "amount": 5000, "iban": VALID_IBAN,
        })
        assert resp.status_code == 403


# ============================================================
# Customer API
# ============================================================

class TestCustomerApi:
    def _reg_body(self):
        return {
            "bsn": VALID_BSN, "first_name": "Jan", "last_name": "de Vries",
            "email": "jan@example.nl",
        }

    def test_register_get_consent_export_erase(self):
        client = TestClient(customer_app(build_platform().customer))
        resp = client.post("/customers", headers=AGENT, json=self._reg_body())
        assert resp.status_code == 201
        cid = resp.json()["id"]

        assert client.get(
            f"/customers/{cid}", headers=AGENT, params={"purpose": "servicing"}
        ).status_code == 200

        consent = client.put(
            f"/customers/{cid}/consent", headers=CUSTOMER,
            json={"consent_type": "marketing", "granted": True},
        )
        assert consent.status_code == 200

        export = client.get(f"/customers/{cid}/export", headers=MANAGER)
        assert export.json()["success"] is True

        erase = client.request(
            "DELETE", f"/customers/{cid}", headers=MANAGER
        )
        assert erase.json()["success"] is True

    def test_register_bad_bsn_returns_422(self):
        client = TestClient(customer_app(build_platform().customer))
        body = self._reg_body()
        body["bsn"] = "123456789"
        assert client.post("/customers", headers=AGENT, json=body).status_code == 422

    def test_get_missing_returns_404(self):
        client = TestClient(customer_app(build_platform().customer))
        assert client.get("/customers/nope", headers=AGENT).status_code == 404


# ============================================================
# Claims API
# ============================================================

class TestClaimsApi:
    def _seed_active_policy(self, platform, customer_id="CUST-1"):
        async def seed():
            from modernized.services.policy.models import PolicyApplication
            app = PolicyApplication(
                customer_id=customer_id, policy_type="auto",
                coverage_amount=1_000_000,
                start_date=datetime.now() - timedelta(days=1),
                end_date=datetime.now() + timedelta(days=365),
            )
            pol = await platform.policy.create_policy(app, "agent1", "agent")
            await platform.policy.activate_policy(pol.id, "mgr", "manager")
            return pol.id

        return asyncio.run(seed())

    def test_health(self):
        client = TestClient(claims_app(build_platform().claims))
        assert client.get("/health").json()["service"] == "claims"

    def test_submit_and_get(self):
        platform = build_platform()
        pid = self._seed_active_policy(platform)
        client = TestClient(claims_app(platform.claims))
        resp = client.post(
            "/claims", headers=CUSTOMER, params={"customer_id": "CUST-1"},
            json={
                "policy_id": pid, "claim_type": "auto",
                "description": "Schade aan de auto na botsing op snelweg",
                "amount_claimed": 5000, "incident_date": _iso(-2),
            },
        )
        assert resp.status_code == 201
        claim_id = resp.json()["id"]
        assert client.get(f"/claims/{claim_id}").status_code == 200

    def test_submit_unowned_returns_403(self):
        platform = build_platform()
        pid = self._seed_active_policy(platform, customer_id="OTHER")
        client = TestClient(claims_app(platform.claims))
        resp = client.post(
            "/claims", headers=CUSTOMER, params={"customer_id": "CUST-1"},
            json={
                "policy_id": pid, "claim_type": "auto",
                "description": "Schade aan de auto na botsing op snelweg",
                "amount_claimed": 5000, "incident_date": _iso(-2),
            },
        )
        assert resp.status_code == 403

    def test_get_missing_returns_404(self):
        client = TestClient(claims_app(build_platform().claims))
        assert client.get("/claims/nope").status_code == 404
