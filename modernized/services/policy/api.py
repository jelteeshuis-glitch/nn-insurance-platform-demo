"""
Policy Service — REST API (FastAPI)

Thin HTTP layer over :class:`PolicyService`.
"""
from fastapi import Depends, FastAPI, HTTPException

from ...shared.http import Actor, get_actor, register_exception_handlers
from .models import PolicyApplication
from .service import PolicyService


def create_app(service: PolicyService) -> FastAPI:
    app = FastAPI(title="NN Policy Service", version="1.0.0")
    register_exception_handlers(app)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "policy"}

    @app.post("/policies", status_code=201)
    async def create_policy(
        application: PolicyApplication, actor: Actor = Depends(get_actor)
    ) -> dict:
        policy = await service.create_policy(application, actor.actor, actor.role)
        return policy.model_dump(mode="json")

    @app.get("/policies/{policy_id}")
    async def get_policy(policy_id: str) -> dict:
        policy = await service.get_policy(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        return policy.model_dump(mode="json")

    @app.post("/policies/{policy_id}/activate")
    async def activate(policy_id: str, actor: Actor = Depends(get_actor)) -> dict:
        policy = await service.activate_policy(policy_id, actor.actor, actor.role)
        return policy.model_dump(mode="json")

    @app.post("/policies/{policy_id}/suspend")
    async def suspend(
        policy_id: str, reason: str, actor: Actor = Depends(get_actor)
    ) -> dict:
        policy = await service.suspend_policy(policy_id, reason, actor.actor, actor.role)
        return policy.model_dump(mode="json")

    @app.post("/policies/{policy_id}/cancel")
    async def cancel(
        policy_id: str, reason: str, actor: Actor = Depends(get_actor)
    ) -> dict:
        policy = await service.cancel_policy(policy_id, reason, actor.actor, actor.role)
        return policy.model_dump(mode="json")

    @app.get("/policies/{policy_id}/coverage")
    async def coverage(policy_id: str, amount: float) -> dict:
        result = await service.verify_coverage(policy_id, amount)
        return result.model_dump(mode="json")

    return app


def build_default_app() -> FastAPI:
    from ...platform import build_platform
    return create_app(build_platform().policy)


app = build_default_app()
