"""
Claims Service — REST API (FastAPI)

Thin HTTP layer over :class:`ClaimsService`, replacing the monolithic Flask
routes in ``legacy/src/app.py``. Business logic lives in the service; routes
only translate HTTP ↔ domain calls. Caller identity/role come from the
``X-Actor`` / ``X-Actor-Role`` headers (a real deployment resolves these from a
validated JWT).
"""
from fastapi import Depends, FastAPI, HTTPException

from ...shared.http import Actor, get_actor, register_exception_handlers
from .models import ClaimDecision, ClaimStatus, ClaimSubmission
from .service import ClaimsService


def create_app(service: ClaimsService) -> FastAPI:
    app = FastAPI(title="NN Claims Service", version="1.0.0")
    register_exception_handlers(app)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "claims"}

    @app.post("/claims", status_code=201)
    async def submit_claim(
        submission: ClaimSubmission, customer_id: str, actor: Actor = Depends(get_actor)
    ) -> dict:
        claim = await service.submit_claim(submission, customer_id, actor.actor)
        return claim.model_dump(mode="json")

    @app.get("/claims/{claim_id}")
    async def get_claim(claim_id: str) -> dict:
        claim = await service.repository.get(claim_id)
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        return claim.model_dump(mode="json")

    @app.post("/claims/{claim_id}/advance")
    async def advance(
        claim_id: str, status: ClaimStatus, actor: Actor = Depends(get_actor)
    ) -> dict:
        claim = await service.advance_status(claim_id, status, actor.actor, actor.role)
        return claim.model_dump(mode="json")

    @app.post("/claims/decision")
    async def decide(
        decision: ClaimDecision, actor: Actor = Depends(get_actor)
    ) -> dict:
        claim = await service.process_decision(decision, actor.actor, actor.role)
        return claim.model_dump(mode="json")

    @app.post("/claims/{claim_id}/flag")
    async def flag(
        claim_id: str, reason: str, fraud_score: float,
        actor: Actor = Depends(get_actor),
    ) -> dict:
        claim = await service.flag_claim(claim_id, reason, fraud_score, actor.actor)
        return claim.model_dump(mode="json")

    return app


def build_default_app() -> FastAPI:
    """Build a standalone app backed by a fresh in-process platform."""
    from ...platform import build_platform
    return create_app(build_platform().claims)


app = build_default_app()
