"""
Notification Service — Event Consumer

A minimal, decoupled notification sink. In the legacy monolith notifications
were sent inline inside claims/payment logic (see ``send_notification`` in
``legacy/src/utils.py``), so an SMTP failure could leave a claim in an
inconsistent state. Here notifications are a downstream event consumer: failures
are isolated and land in the event bus dead-letter queue instead of corrupting
business transactions.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from governance.audit.audit_logger import PIIDetector

from .events import DomainEvent


@dataclass
class Notification:
    """A single outbound notification (channel-agnostic)."""

    event_type: str
    message: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class NotificationService:
    """Collects notifications triggered by domain events.

    Messages are PII-masked before storage so no BSN/IBAN/email leaks into the
    notification log (GDPR / ADR-003).
    """

    def __init__(self) -> None:
        self.sent: list[Notification] = []

    async def handle_event(self, event: DomainEvent) -> None:
        """Generic event handler — turns a domain event into a notification."""
        raw = f"Event {event.event_type}: {event.payload}"
        self.sent.append(
            Notification(event_type=event.event_type, message=PIIDetector.mask(raw))
        )

    def notifications_for(self, event_type: str) -> list[Notification]:
        return [n for n in self.sent if n.event_type == event_type]
