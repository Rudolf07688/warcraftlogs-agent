"""WebSocket: streaming chat turns (see contracts/websocket.md).

One turn is processed at a time per socket (the receive loop awaits each turn to
completion), so turns on a single socket are naturally serialized rather than
racing.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ..agent_runner import stream_response
from ..config import settings
from ..db import repository as repo
from ..db.session import SessionLocal
from ..schemas import ChatTurn, DoneFrame, ErrorFrame, MetaFrame

router = APIRouter()


async def _send(ws: WebSocket, frame) -> None:
    payload = frame.model_dump(mode="json") if hasattr(frame, "model_dump") else frame
    await ws.send_json(payload)


async def _handle_turn(ws: WebSocket, turn: ChatTurn) -> None:
    async with SessionLocal() as session:
        # Resolve or create the conversation.
        if turn.conversation_id is not None:
            conv = await repo.get_conversation(session, turn.conversation_id)
            if conv is None:
                await _send(ws, ErrorFrame(code="not_found", message="Conversation not found."))
                return
        else:
            conv = await repo.create_conversation(session, model=turn.model)
        conv_id = conv.id

        # Persist the user message, then announce the turn.
        user_msg = await repo.add_message(session, conv_id, "user", turn.content)
        await session.commit()
        await _send(ws, MetaFrame(conversation_id=conv_id, seq=user_msg.seq))

        # Stream the agent response, accumulating tokens into the final content.
        tokens: list[str] = []
        try:
            async for frame in stream_response(turn.model, str(conv_id), turn.content):
                if frame.get("type") == "token":
                    tokens.append(frame["text"])
                await ws.send_json(frame)
        except Exception as exc:  # noqa: BLE001 - surface failure to the client
            await _send(ws, ErrorFrame(code="agent_error", message=str(exc)))
            return

        final_text = "".join(tokens) or "(no response)"
        agent_msg = await repo.add_message(session, conv_id, "agent", final_text)
        await session.commit()
        await _send(ws, DoneFrame(message_id=agent_msg.id))


@router.websocket("/ws/chat")
async def chat(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_json()
            try:
                turn = ChatTurn(**raw)
            except ValidationError:
                await _send(ws, ErrorFrame(code="empty_message", message="Invalid or empty message."))
                continue
            if turn.model not in settings.model_list:
                await _send(ws, ErrorFrame(code="invalid_model", message=f"Unknown model '{turn.model}'."))
                continue
            await _handle_turn(ws, turn)
    except WebSocketDisconnect:
        return
