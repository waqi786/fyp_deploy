"""Messaging: new data triggers the next processing stage automatically.

Topics:  raw.ingested → etl.completed → analytics.completed → index.completed

With KAFKA_BOOTSTRAP_SERVERS set (and kafka-python installed) events are published to Kafka so separate workers can
consume them. Without Kafka, events are appended to the lake (events/<topic>/<date>.jsonl, an audit log) and
delivered in-process to subscribed handlers, so the same pipeline runs on a laptop with no extra services.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from resora_pipeline.lake import DataLake

logger = logging.getLogger(__name__)

TOPICS = ("raw.ingested", "etl.completed", "analytics.completed", "index.completed")
Handler = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self, lake: DataLake | None = None) -> None:
        self.lake = lake
        self.handlers: dict[str, list[Handler]] = defaultdict(list)
        self.published: list[dict[str, Any]] = []

    def subscribe(self, topic: str, handler: Handler) -> None:
        if topic not in TOPICS:
            raise ValueError(f"unknown topic {topic}")
        self.handlers[topic].append(handler)

    def _envelope(self, topic: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"event_id": uuid.uuid4().hex, "topic": topic, "at": datetime.now(UTC).isoformat(), "payload": payload}

    def publish(self, topic: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = self._envelope(topic, payload)
        self.published.append(event)
        self._log(event)
        for handler in list(self.handlers.get(topic, [])):
            handler(event)
        return event

    def _log(self, event: dict[str, Any]) -> None:
        if self.lake is None:
            return
        key = f"events/{event['topic']}/{event['at'][:10]}.jsonl"
        try:
            existing = self.lake.storage.get_bytes(key) if self.lake.storage.exists(key) else b""
            self.lake.storage.put_bytes(key, existing + json.dumps(event, sort_keys=True).encode() + b"\n", "application/x-ndjson")
        except Exception:  # noqa: BLE001 - the audit log must never break processing
            logger.warning("could not append event %s to the lake", event["topic"])


class KafkaEventBus(EventBus):  # pragma: no cover - requires a Kafka broker
    def __init__(self, bootstrap_servers: str, lake: DataLake | None = None) -> None:
        super().__init__(lake)
        from kafka import KafkaProducer  # optional dependency: pip install resora-pipeline[kafka]

        self.producer = KafkaProducer(bootstrap_servers=bootstrap_servers.split(","), value_serializer=lambda value: json.dumps(value).encode(), acks="all", retries=5)

    def publish(self, topic: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = self._envelope(topic, payload)
        self.producer.send(f"resora.{topic}", event)
        self.producer.flush(timeout=10)
        self.published.append(event)
        self._log(event)
        for handler in list(self.handlers.get(topic, [])):
            handler(event)
        return event


def make_bus(bootstrap_servers: str | None, lake: DataLake | None) -> EventBus:
    if bootstrap_servers:
        try:
            return KafkaEventBus(bootstrap_servers, lake)
        except Exception as error:  # noqa: BLE001
            logger.warning("Kafka unavailable (%s); using the in-process event bus", type(error).__name__)
    return EventBus(lake)
