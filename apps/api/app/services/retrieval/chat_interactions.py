from datetime import UTC, datetime
from uuid import uuid4


class ChatInteractionStore:
    def __init__(self) -> None:
        self.feedback: dict[str, dict] = {}
        self.pins: dict[str, dict] = {}

    def log_feedback(self, feedback_token: str, rating: int, helpful: bool, note: str | None, user_id: str | None) -> dict:
        feedback_id = f"chatfb-{uuid4().hex[:10]}"
        payload = {
            "feedback_id": feedback_id,
            "feedback_token": feedback_token,
            "rating": rating,
            "helpful": helpful,
            "note": note,
            "user_id": user_id,
            "stored_at": datetime.now(UTC).isoformat(),
        }
        self.feedback[feedback_id] = payload
        return payload

    def pin_answer(
        self,
        feedback_token: str,
        shareable_thread_token: str,
        answer: str,
        starred: bool,
        user_id: str | None,
    ) -> dict:
        pin_id = f"pin-{uuid4().hex[:10]}"
        payload = {
            "pin_id": pin_id,
            "feedback_token": feedback_token,
            "shareable_thread_token": shareable_thread_token,
            "answer": answer,
            "pinned": True,
            "starred": starred,
            "user_id": user_id,
            "stored_at": datetime.now(UTC).isoformat(),
        }
        self.pins[pin_id] = payload
        return payload
