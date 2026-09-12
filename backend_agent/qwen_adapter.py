from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from collections.abc import AsyncIterator

from .config import Settings
from .fun_realtime.client import RealtimeClient
from .prompts import compile_prompt
from .profiles import get_profile

log = logging.getLogger(__name__)


class QwenOmniRealtimeAdapter:
    """Production adapter built on Alibaba's fun-audiochat-realtime client.

    The browser never receives provider credentials. This layer owns the
    provider socket, response cancellation and event normalization; policy,
    persistence and RAG stay in the API layer.
    """

    def __init__(self, settings: Settings, *, agent_id: str, rag_timeout: float = 2.0):
        self.settings = settings
        self.agent_id = agent_id
        self.rag_timeout = rag_timeout
        self.client: RealtimeClient | None = None
        # Compatibility handle used by the existing protocol smoke test.
        self.ws = None
        self.base_prompt = compile_prompt(agent_id)
        self.response_active = False

    async def connect(self) -> None:
        if not self.settings.qwen_ready:
            raise RuntimeError("QWEN_CONFIG_MISSING")
        extra_headers = {"X-DashScope-Space": self.settings.space_id} if self.settings.space_id else {}
        self.client = RealtimeClient(
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
            model=self.settings.model,
            extra_headers=extra_headers,
        )
        await self.client.connect()
        self.ws = self.client._ws
        profile = get_profile(self.agent_id)
        voice = (profile.get("voice") or {}).get("voice") or "longanqian"
        await self.send({
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": self.base_prompt,
                "voice": voice,
                "input_audio_format": "pcm",
                "output_audio_format": "pcm",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.25,
                    "silence_duration_ms": 1000,
                    "prefix_padding_ms": 300,
                    "create_response": False,
                    "interrupt_response": True,
                },
                "input_audio_transcription": {"language": "zh"},
            },
        })

    async def close(self) -> None:
        if self.client:
            await self.client.close()
            self.client = None
        self.ws = None
        self.response_active = False

    async def send(self, event: dict) -> None:
        if not self.client:
            raise RuntimeError("QWEN_NOT_CONNECTED")
        event.setdefault("event_id", f"evt_{uuid.uuid4().hex}")
        # Mark immediately when a response request is sent so an early VAD
        # speech_started event can cancel the in-flight request before the
        # provider emits response.created.
        if event.get("type") == "response.create":
            self.response_active = True
        elif event.get("type") in {"response.cancel", "response.done", "response.cancelled"}:
            self.response_active = False
        await self.client.send_event(event)

    async def send_pcm(self, pcm: bytes) -> None:
        if not self.client:
            raise RuntimeError("QWEN_NOT_CONNECTED")
        await self.client.send_audio(pcm)

    async def cancel_response(self) -> bool:
        if not self.response_active:
            return False
        await self.send({"type": "response.cancel"})
        self.response_active = False
        return True

    async def events(self) -> AsyncIterator[dict]:
        if not self.client:
            return
        async for event in self.client:
            data = event.raw
            event_type = data.get("type")
            if event_type == "response.created":
                self.response_active = True
            elif event_type in {"response.done", "response.audio.done", "response.cancelled"}:
                self.response_active = False
            # RAG is triggered only after provider final ASR, never on deltas.
            if event_type in {"conversation.item.input_audio_transcription.completed", "input_audio_buffer.committed"}:
                data["turn_id"] = data.get("turn_id") or f"turn_{uuid.uuid4().hex}"
                data["rag_status"] = "pending_final_asr"
            yield data

    async def compile_turn_prompt(self, turn_id: str, user_text: str, rag_loader) -> dict:
        try:
            rag = await asyncio.wait_for(rag_loader(user_text), timeout=self.rag_timeout)
            rag_status = "ready" if rag else "empty"
        except asyncio.TimeoutError:
            rag, rag_status = "timeout_fallback", "timeout_fallback"
        prompt = compile_prompt(self.agent_id, user_text=user_text, rag=rag if rag_status == "ready" else "")
        return {"turn_id": turn_id, "prompt": prompt, "rag_status": rag_status}
