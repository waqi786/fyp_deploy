import asyncio

from app.schemas.search import SearchAlertRunResponse
from app.services.notifications.delivery import AlertDeliveryService


class FakeSender:
    def __init__(self) -> None:
        self.messages = []

    def send_message(self, message):  # noqa: ANN001
        self.messages.append(message)


def make_alert_run() -> SearchAlertRunResponse:
    return SearchAlertRunResponse(
        user_id="user-1",
        evaluated_count=1,
        triggered_count=1,
        notifications=[
            {
                "saved_search_id": "saved-1",
                "query": "retrieval benchmark",
                "cadence": "daily",
                "new_match_count": 1,
                "matched_titles": ["Retrieval Benchmark Dataset"],
            }
        ],
        generated_at="2026-07-10T10:00:00Z",
    )


def test_alert_delivery_sends_email_with_configured_sender() -> None:
    sender = FakeSender()
    result = asyncio.run(
        AlertDeliveryService(smtp_sender=sender).deliver(make_alert_run(), recipient_email="user@example.org")
    )
    assert result.email_delivered is True
    assert result.attempted_notifications == 1
    assert sender.messages
    assert "Retrieval Benchmark Dataset" in sender.messages[0].get_content()


def test_alert_delivery_is_safe_without_provider() -> None:
    result = asyncio.run(AlertDeliveryService().deliver(make_alert_run()))
    assert result.email_delivered is False
    assert result.webhook_delivered is False
    assert result.detail == "no delivery provider configured"
