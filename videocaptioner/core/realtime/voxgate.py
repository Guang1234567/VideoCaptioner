"""Client for the local voxgate realtime transcription endpoint."""

import asyncio
import base64
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

import aiohttp

VoxgateEventType = Literal["session", "delta", "completed", "error"]


@dataclass(frozen=True)
class VoxgateRealtimeEvent:
    """A normalized realtime transcription event from voxgate."""

    type: VoxgateEventType
    text: str = ""
    item_id: str = ""
    raw_type: str = ""
    raw: dict[str, Any] | None = None


class VoxgateRealtimeClient:
    """OpenAI Realtime-style client for voxgate's local WebSocket endpoint."""

    def __init__(
        self,
        url: str = "ws://127.0.0.1:8080/v1/realtime",
        *,
        auth_token: str = "",
        idle_timeout: float = 8.0,
    ):
        self.url = url
        self.auth_token = auth_token
        self.idle_timeout = idle_timeout

    async def stream_pcm(
        self,
        pcm_chunks: AsyncIterator[bytes],
        *,
        commit_when_done: bool = True,
    ) -> AsyncIterator[VoxgateRealtimeEvent]:
        """Send 16 kHz mono PCM16 chunks and yield normalized transcript events."""

        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.url, headers=headers) as ws:
                await ws.send_json({"type": "session.update", "session": {"type": "transcription"}})
                queue: asyncio.Queue[VoxgateRealtimeEvent | None] = asyncio.Queue()
                sender = asyncio.create_task(self._send_pcm(ws, pcm_chunks, commit_when_done))
                receiver = asyncio.create_task(self._receive_events(ws, queue, sender))

                try:
                    while True:
                        event = await queue.get()
                        if event is None:
                            break
                        yield event
                finally:
                    sender.cancel()
                    receiver.cancel()
                    await asyncio.gather(sender, receiver, return_exceptions=True)

    async def _send_pcm(
        self,
        ws: aiohttp.ClientWebSocketResponse,
        pcm_chunks: AsyncIterator[bytes],
        commit_when_done: bool,
    ) -> None:
        async for pcm in pcm_chunks:
            if not pcm:
                continue
            await ws.send_json(
                {
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(pcm).decode("ascii"),
                }
            )
        if commit_when_done:
            await ws.send_json({"type": "input_audio_buffer.commit"})

    async def _receive_events(
        self,
        ws: aiohttp.ClientWebSocketResponse,
        queue: asyncio.Queue[VoxgateRealtimeEvent | None],
        sender: asyncio.Task,
    ) -> None:
        try:
            while True:
                timeout = self.idle_timeout if sender.done() else None
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
                except asyncio.TimeoutError:
                    break
                if msg.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR}:
                    break
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                event = normalize_voxgate_message(msg.json())
                if event is None:
                    continue
                await queue.put(event)
                if sender.done() and event.type in {"completed", "error"}:
                    break
        finally:
            await queue.put(None)


def normalize_voxgate_message(message: dict[str, Any]) -> VoxgateRealtimeEvent | None:
    """Normalize raw voxgate realtime JSON into a small app-facing event model."""

    raw_type = str(message.get("type", ""))
    if raw_type in {"session.created", "session.updated"}:
        return VoxgateRealtimeEvent(type="session", raw_type=raw_type, raw=message)
    if raw_type == "conversation.item.input_audio_transcription.delta":
        return VoxgateRealtimeEvent(
            type="delta",
            text=str(message.get("delta", "")),
            item_id=str(message.get("item_id", "")),
            raw_type=raw_type,
            raw=message,
        )
    if raw_type == "conversation.item.input_audio_transcription.completed":
        return VoxgateRealtimeEvent(
            type="completed",
            text=str(message.get("transcript", "")),
            item_id=str(message.get("item_id", "")),
            raw_type=raw_type,
            raw=message,
        )
    if raw_type in {"conversation.item.input_audio_transcription.failed", "error"}:
        error = message.get("error")
        text = str(error.get("message", "")) if isinstance(error, dict) else str(message)
        return VoxgateRealtimeEvent(
            type="error",
            text=text,
            item_id=str(message.get("item_id", "")),
            raw_type=raw_type,
            raw=message,
        )
    return None
