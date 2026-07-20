"""
Bank Client — External Payment Rail Adapter

Isolates the (simulated) banking API behind an async interface so the payment
service can be tested deterministically and wrapped by a circuit breaker.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any


class BankClient(ABC):
    """Abstract async bank transfer client."""

    @abstractmethod
    async def transfer(
        self, iban_token: str, amount: float, currency: str, reference: str
    ) -> dict[str, Any]:
        """Execute a transfer and return a result with a bank ``reference``."""


class SimulatedBankClient(BankClient):
    """Always-succeeds bank client for the demo/happy path."""

    async def transfer(
        self, iban_token: str, amount: float, currency: str, reference: str
    ) -> dict[str, Any]:
        return {
            "reference": f"BANK-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "status": "ok",
        }


class FailingBankClient(BankClient):
    """Bank client that always raises — used to exercise failure paths."""

    async def transfer(
        self, iban_token: str, amount: float, currency: str, reference: str
    ) -> dict[str, Any]:
        raise ConnectionError("Bank API unavailable")
