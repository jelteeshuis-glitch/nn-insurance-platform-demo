"""
Payment Service — REST API (FastAPI)

Thin HTTP layer over :class:`PaymentService`.
"""
from fastapi import Depends, FastAPI, HTTPException

from ...shared.http import Actor, get_actor, register_exception_handlers
from .models import PaymentInstruction, RefundRequest
from .service import PaymentService


def create_app(service: PaymentService) -> FastAPI:
    app = FastAPI(title="NN Payment Service", version="1.0.0")
    register_exception_handlers(app)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "payments"}

    @app.post("/payments", status_code=201)
    async def process_payment(
        instruction: PaymentInstruction, actor: Actor = Depends(get_actor)
    ) -> dict:
        payment = await service.process_payment(instruction, actor.actor, actor.role)
        return payment.model_dump(mode="json")

    @app.get("/payments/{payment_id}")
    async def get_payment(payment_id: str) -> dict:
        payment = await service.repository.get(payment_id)
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        return payment.model_dump(mode="json")

    @app.post("/payments/refund")
    async def refund(
        request: RefundRequest, actor: Actor = Depends(get_actor)
    ) -> dict:
        payment = await service.process_refund(request, actor.actor, actor.role)
        return payment.model_dump(mode="json")

    return app


def build_default_app() -> FastAPI:
    from ...platform import build_platform
    return create_app(build_platform().payments)


app = build_default_app()
