"""
Payment persistence — in-memory implementation with an idempotency index.
"""
from typing import Optional

from ...shared.repository import InMemoryRepository
from .models import Payment


class PaymentRepository(InMemoryRepository[Payment]):
    """In-memory payment store keyed by id with a secondary idempotency index."""

    async def get_by_idempotency_key(self, key: str) -> Optional[Payment]:
        """Look up a payment by its idempotency key (prevents double-payout)."""
        for payment in self._store.values():
            if payment.idempotency_key == key:
                return payment
        return None
