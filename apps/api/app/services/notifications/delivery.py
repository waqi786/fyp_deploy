from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import httpx

from app.core.config import settings
from app.schemas.search import SearchAlertRunResponse


class SmtpSender(Protocol):
    def send_message(self, message: EmailMessage) -> object:
        ...


@dataclass(frozen=True)
class AlertDeliveryResult:
    webhook_delivered: bool
    email_delivered: bool
    attempted_notifications: int
    detail: str


class AlertDeliveryService:
    def __init__(self, *, smtp_sender: SmtpSender | None = None) -> None:
        self.smtp_sender = smtp_sender

    async def deliver(self, alert_run: SearchAlertRunResponse, *, recipient_email: str | None = None) -> AlertDeliveryResult:
        webhook_delivered = await self._deliver_webhook(alert_run)
        email_delivered = self._deliver_email(alert_run, recipient_email=recipient_email)
        detail = "delivered" if webhook_delivered or email_delivered else "no delivery provider configured"
        return AlertDeliveryResult(
            webhook_delivered=webhook_delivered,
            email_delivered=email_delivered,
            attempted_notifications=len(alert_run.notifications),
            detail=detail,
        )

    async def _deliver_webhook(self, alert_run: SearchAlertRunResponse) -> bool:
        if not settings.alert_delivery_webhook_url or not alert_run.notifications:
            return False
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.post(
                    settings.alert_delivery_webhook_url,
                    json=alert_run.model_dump(mode="json"),
                )
            return 200 <= response.status_code < 300
        except httpx.HTTPError:
            return False

    def _deliver_email(self, alert_run: SearchAlertRunResponse, *, recipient_email: str | None) -> bool:
        if not recipient_email or not alert_run.notifications:
            return False
        sender = self.smtp_sender or self._smtp_sender()
        if sender is None:
            return False
        message = EmailMessage()
        message["Subject"] = f"Resora saved-search alerts: {alert_run.triggered_count} updates"
        message["From"] = settings.smtp_from_email
        message["To"] = recipient_email
        lines = [
            f"Resora found {alert_run.triggered_count} saved-search alert updates.",
            "",
        ]
        for notification in alert_run.notifications:
            lines.append(f"Query: {notification['query']}")
            for title in notification.get("matched_titles", []):
                lines.append(f"- {title}")
            lines.append("")
        message.set_content("\n".join(lines))
        try:
            sender.send_message(message)
            return True
        except (OSError, smtplib.SMTPException):
            return False

    def _smtp_sender(self) -> SmtpSender | None:
        if not settings.smtp_host:
            return None
        try:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8)
            server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            return server
        except (OSError, smtplib.SMTPException):
            return None
