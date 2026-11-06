from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass
class SessionCache:
    ttl_seconds: int = 3600
    store: dict[str, tuple[dict, datetime]] = field(default_factory=dict)

    def set(self, session_id: str, payload: dict) -> None:
        self.store[session_id] = (payload, datetime.now(UTC))

    def get(self, session_id: str) -> dict | None:
        entry = self.store.get(session_id)
        if not entry:
            return None
        payload, timestamp = entry
        if datetime.now(UTC) - timestamp > timedelta(seconds=self.ttl_seconds):
            self.store.pop(session_id, None)
            return None
        return payload

    def append_turn(self, session_id: str, question: str, answer: str, citations: list[str]) -> dict:
        existing = self.get(session_id) or {"turns": [], "last_question": None, "last_answer": None, "citations": []}
        turns = list(existing.get("turns", []))
        turns.append(
            {
                "question": question,
                "answer": answer,
                "citations": citations,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        payload = {
            "turns": turns[-20:],
            "last_question": question,
            "last_answer": answer,
            "citations": citations,
        }
        self.set(session_id, payload)
        return payload
