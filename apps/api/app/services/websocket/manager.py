from collections import defaultdict

from fastapi import WebSocket

from app.core.config import settings


class WebSocketManager:
    def __init__(self) -> None:
        self.rooms: defaultdict[str, list[WebSocket]] = defaultdict(list)
        self.history: defaultdict[str, list[str]] = defaultdict(list)

    async def connect(self, room: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.rooms[room].append(websocket)

    def disconnect(self, room: str, websocket: WebSocket) -> None:
        if websocket in self.rooms[room]:
            self.rooms[room].remove(websocket)

    async def broadcast(self, room: str, message: str) -> None:
        self.history[room].append(message)
        self.history[room] = self.history[room][-settings.websocket_history_limit :]
        for connection in list(self.rooms[room]):
            await connection.send_text(message)


manager = WebSocketManager()
