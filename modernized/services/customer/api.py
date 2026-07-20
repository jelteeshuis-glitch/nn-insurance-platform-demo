"""
Customer Service — REST API (FastAPI)

Thin HTTP layer over :class:`CustomerService`.
"""
from fastapi import Depends, FastAPI, HTTPException

from ...shared.http import Actor, get_actor, register_exception_handlers
from .models import ConsentUpdate, CustomerRegistration
from .service import CustomerService


def create_app(service: CustomerService) -> FastAPI:
    app = FastAPI(title="NN Customer Service", version="1.0.0")
    register_exception_handlers(app)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "customer"}

    @app.post("/customers", status_code=201)
    async def register(
        registration: CustomerRegistration, actor: Actor = Depends(get_actor)
    ) -> dict:
        customer = await service.register_customer(registration, actor.actor, actor.role)
        return customer.model_dump(mode="json")

    @app.get("/customers/{customer_id}")
    async def get_customer(
        customer_id: str, purpose: str = "servicing",
        actor: Actor = Depends(get_actor),
    ) -> dict:
        customer = await service.get_customer(
            customer_id, purpose, actor.actor, actor.role
        )
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        return customer.model_dump(mode="json")

    @app.put("/customers/{customer_id}/consent")
    async def update_consent(
        customer_id: str, update: ConsentUpdate, actor: Actor = Depends(get_actor)
    ) -> dict:
        customer = await service.update_consent(
            customer_id, update, actor.actor, actor.role
        )
        return customer.model_dump(mode="json")

    @app.delete("/customers/{customer_id}")
    async def erase(customer_id: str, actor: Actor = Depends(get_actor)) -> dict:
        return await service.right_to_erasure(customer_id, actor.actor, actor.role)

    @app.get("/customers/{customer_id}/export")
    async def export(customer_id: str, actor: Actor = Depends(get_actor)) -> dict:
        return await service.data_portability(customer_id, actor.actor, actor.role)

    return app


def build_default_app() -> FastAPI:
    from ...platform import build_platform
    return create_app(build_platform().customer)


app = build_default_app()
