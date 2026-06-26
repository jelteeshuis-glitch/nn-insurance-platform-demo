"""
Event Bus — Async Event-Driven Architecture

Decouples services via domain events. Each service publishes events
that other services can subscribe to without direct coupling.

Benefits over legacy approach:
- Services don't know about each other
- Failure in one service doesn't cascade
- Easy to add new consumers (notifications, analytics)
- Natural audit trail
- Supports eventual consistency
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine
from uuid import uuid4


@dataclass
class DomainEvent:
    """A domain event — something that happened in the system."""
    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_service: str = ""
    correlation_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "source_service": self.source_service,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
            "metadata": self.metadata,
        })


EventHandler = Callable[[DomainEvent], Coroutine[Any, Any, None]]


class EventBus:
    """In-process event bus (production would use Kafka/RabbitMQ/Azure Service Bus)."""

    def __init__(self, service_name: str = "unknown"):
        self.service_name = service_name
        self._handlers: dict[str, list[EventHandler]] = {}
        self._dead_letter: list[DomainEvent] = []

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe to events of a specific type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(
        self, event_type: str, payload: dict[str, Any], correlation_id: str = ""
    ) -> DomainEvent:
        """Publish a domain event to all subscribers."""
        event = DomainEvent(
            event_type=event_type,
            source_service=self.service_name,
            correlation_id=correlation_id or str(uuid4()),
            payload=payload,
        )

        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                # Failed delivery → dead letter queue
                event.metadata["error"] = str(e)
                event.metadata["failed_handler"] = handler.__name__
                self._dead_letter.append(event)

        return event

    def get_dead_letters(self) -> list[DomainEvent]:
        """Retrieve failed events for investigation."""
        return self._dead_letter.copy()
