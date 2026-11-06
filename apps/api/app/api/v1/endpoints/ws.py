from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket.manager import manager


router = APIRouter()


@router.websocket("/chat/{session_id}")
async def chat_socket(websocket: WebSocket, session_id: str) -> None:
    await manager.connect(f"chat:{session_id}", websocket)
    try:
        while True:
            message = await websocket.receive_text()
            await manager.broadcast(f"chat:{session_id}", message)
    except WebSocketDisconnect:
        manager.disconnect(f"chat:{session_id}", websocket)


@router.websocket("/workspace/{workspace_id}")
async def workspace_socket(websocket: WebSocket, workspace_id: str) -> None:
    await manager.connect(f"workspace:{workspace_id}", websocket)
    try:
        while True:
            message = await websocket.receive_text()
            await manager.broadcast(f"workspace:{workspace_id}", message)
    except WebSocketDisconnect:
        manager.disconnect(f"workspace:{workspace_id}", websocket)
