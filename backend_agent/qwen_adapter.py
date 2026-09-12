from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from collections.abc import AsyncIterator

import websockets

from .config import Settings
from .prompts import compile_prompt

log = logging.getLogger(__name__)


class QwenOmniRealtimeAdapter:
    """One browser session to one Qwen Omni Realtime connection.

    The adapter is deliberately provider-facing only: persistence and policy
    remain in the API layer, while every accepted Final ASR turn is tagged with
    one ``turn_id`` before RAG and response events are emitted.
    """

    def __init__(self, settings: Settings, *, agent_id: str, rag_timeout: float = 2.0):
        self.settings = settings
        self.agent_id = agent_id
        self.rag_timeout = rag_timeout
        self.ws = None
        self.base_prompt = compile_prompt(agent_id)

    async def connect(self) -> None:
        if not self.settings.qwen_ready:
            raise RuntimeError("QWEN_CONFIG_MISSING")
        url = f"{self.settings.base_url}?model={self.settings.model}"
        headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        if self.settings.space_id:
            headers["X-DashScope-Space"] = self.settings.space_id
        self.ws = await websockets.connect(url, additional_headers=headers, max_size=None, open_timeout=12)
        await self.send({"type": "session.update", "session": {"instructions": self.base_prompt, "voice": "Ethan", "turn_detection": {"type": "server_vad", "threshold": 0.25, "silence_duration_ms": 3500, "prefix_padding_ms": 300}}})

    async def close(self) -> None:
        if self.ws:
            await self.ws.close(code=1000)
            self.ws = None

    async def send(self, event: dict) -> None:
        if not self.ws:
            raise RuntimeError("QWEN_NOT_CONNECTED")
        event.setdefault("event_id", f"evt_{uuid.uuid4().hex}")
        await self.ws.send(json.dumps(event, ensure_ascii=False))

    async def send_pcm(self, pcm: bytes) -> None:
        await self.send({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode("ascii")})

    async def events(self) -> AsyncIterator[dict]:
        if not self.ws:
            return
        async for raw in self.ws:
            data = json.loads(raw)
            # RAG is triggered only after provider final ASR, never on deltas.
            if data.get("type") in {"conversation.item.input_audio_transcription.completed", "input_audio_buffer.committed"}:
                data["turn_id"] = data.get("turn_id") or f"turn_{uuid.uuid4().hex}"
                data["rag_status"] = "pending_final_asr"
            yield data

    async def compile_turn_prompt(self, turn_id: str, user_text: str, rag_loader) -> dict:
        try:
            rag = await asyncio.wait_for(rag_loader(user_text), timeout=self.rag_timeout)
            rag_status = "ready"
        except asyncio.TimeoutError:
            rag, rag_status = "timeout_fallback", "timeout_fallback"
        prompt = compile_prompt(self.agent_id, user_text=user_text, rag=rag if rag_status == "ready" else "")
        return {"turn_id": turn_id, "prompt": prompt, "rag_status": rag_status}
