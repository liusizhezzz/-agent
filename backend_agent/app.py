from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .config import load_settings
from .matcher import recommend
from .profiles import PROFILES, get_profile
from .prompts import compile_prompt
from .qwen_adapter import QwenOmniRealtimeAdapter
from .memory_summarizer import MemorySummarizer
from .store import Store

logging.basicConfig(level=logging.INFO)
settings = load_settings()
store = Store(settings.db_path)
summarizer = MemorySummarizer(settings)
app = FastAPI(title="微光星球 Agent Backend", version="1.0.0")


def require_internal_token(authorization: str | None = Header(default=None)) -> None:
    if settings.internal_token and authorization != f"Bearer {settings.internal_token}":
        raise HTTPException(401, "unauthorized")


class SessionCreate(BaseModel):
    agent_id: str = "soil"
    background_sound: str = "space"


class RecommendRequest(BaseModel):
    text: str = Field(default="", max_length=2000)


class MemoryEnd(BaseModel):
    source_text: str = Field(default="", max_length=4000)
    title: str = Field(default="星球上的一件小东西", max_length=120)
    summary: str = Field(default="", max_length=500)
    category: str = Field(default="日常事件", max_length=20)
    retention: str = Field(default="pending", pattern="^(object|stone|discard|pending)$")


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True, "qwen_ready": settings.qwen_ready, "model": settings.model}


@app.get("/api/agents")
async def agents(_: None = Depends(require_internal_token)) -> dict[str, Any]:
    return {"agents": PROFILES}


@app.post("/api/agents/recommend")
async def agent_recommend(body: RecommendRequest, _: None = Depends(require_internal_token)) -> dict[str, Any]:
    return recommend(body.text)


@app.post("/api/sessions", status_code=201)
async def create_session(body: SessionCreate, _: None = Depends(require_internal_token)) -> dict[str, Any]:
    profile = get_profile(body.agent_id)
    sound = body.background_sound if body.background_sound in {"wind", "space", "rain", "none"} else profile["backgroundSound"]
    sid = store.create_session(profile["id"], sound)
    return {"id": sid, "agent": profile, "background_sound": sound, "prompt": compile_prompt(profile["id"]), "provider": "qwen-omni-realtime", "qwen_ready": settings.qwen_ready}


@app.post("/api/sessions/{session_id}/end")
async def end_session(session_id: str, body: MemoryEnd, _: None = Depends(require_internal_token)) -> dict[str, Any]:
    agent_id = store.session_agent(session_id)
    if not agent_id:
        raise HTTPException(404, "session_not_found")
    profile = get_profile(agent_id)
    source_text = body.source_text or store.transcript(session_id)
    summary, provider = await summarizer.summarize(source_text, body.summary or profile["representativeLine"])
    title = body.title if body.title != "星球上的一件小东西" else profile["memoryObject"]["name"]
    memory = store.end_session(session_id, profile["id"], title, source_text, summary, body.category, body.retention)
    return {"session_id": session_id, "status": "ended", "memory": memory, "summary_provider": provider}


@app.websocket("/api/sessions/{session_id}/audio")
async def audio_socket(websocket: WebSocket, session_id: str, agent_id: str = "soil", token: str = "") -> None:
    if settings.internal_token and token != settings.internal_token:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    adapter = QwenOmniRealtimeAdapter(settings, agent_id=agent_id)
    try:
        await adapter.connect()
        await websocket.send_json({"type": "session.ready", "session_id": session_id, "provider": "qwen-omni-realtime"})
        async def rag_loader(_: str) -> str:
            # Replace with the deployed CBT-I vector service. A timeout or an
            # unavailable index intentionally returns an empty context.
            return ""

        async def upstream() -> None:
            async for event in adapter.events():
                # Barge-in: stop any in-flight response as soon as Qwen's VAD
                # detects speech. The final ASR event below creates exactly one
                # replacement response for the new turn.
                if event.get("type") == "input_audio_buffer.speech_started":
                    await adapter.cancel_response()
                if event.get("type") == "conversation.item.input_audio_transcription.completed":
                    text = str(event.get("transcript") or event.get("text") or "").strip()
                    turn_id = event.get("turn_id") or "turn_unknown"
                    compiled = await adapter.compile_turn_prompt(turn_id, text, rag_loader)
                    store.add_turn(session_id, text, final_asr=True, rag_status=compiled["rag_status"])
                    # The base role prompt is already active. Avoid a network
                    # session.update on ordinary turns; it adds latency and can
                    # race response.create. Only inject a non-empty RAG result.
                    if compiled["rag_status"] == "ready":
                        await adapter.send({"type": "session.update", "session": {"instructions": compiled["prompt"]}})
                    await adapter.send({"type": "response.create"})
                    event["rag_status"] = compiled["rag_status"]
                    event["turn_id"] = turn_id
                await websocket.send_json(event)
        task = asyncio.create_task(upstream())
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                await adapter.send_pcm(message["bytes"])
            elif message.get("text"):
                event = __import__("json").loads(message["text"])
                # Text turns are already final user input. Persist them for the
                # session transcript while audio turns remain gated on Final ASR.
                if event.get("type") == "conversation.item.create":
                    item = event.get("item") or {}
                    content = item.get("content") or []
                    text_parts = [str(part.get("text") or "").strip() for part in content if part.get("type") == "input_text"]
                    text = " ".join(part for part in text_parts if part)
                    if text:
                        store.add_turn(session_id, text, final_asr=True, rag_status="text_input")
                await adapter.send(event)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logging.exception("audio session failed")
        try:
            await websocket.send_json({"type": "error", "code": str(exc)})
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if 'task' in locals():
            task.cancel()
        await adapter.close()


@app.get("/api/memories/{memory_id}")
async def memory(memory_id: str, _: None = Depends(require_internal_token)) -> dict[str, Any]:
    row = store.db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
    if not row:
        raise HTTPException(404, "memory_not_found")
    return {"memory": dict(row)}


@app.get("/api/sessions/{session_id}/memory")
async def session_memory(session_id: str, _: None = Depends(require_internal_token)) -> dict[str, Any]:
    rows = store.db.execute("SELECT * FROM memories WHERE session_id=? ORDER BY created_at DESC", (session_id,)).fetchall()
    return {"memories": [dict(row) for row in rows]}


@app.get("/api/memories")
async def memories(_: None = Depends(require_internal_token)) -> dict[str, Any]:
    return {"memories": [dict(row) for row in store.db.execute("SELECT * FROM memories ORDER BY created_at DESC").fetchall()]}


@app.patch("/api/memories/{memory_id}/retention")
async def retention(memory_id: str, body: dict[str, str], _: None = Depends(require_internal_token)) -> dict[str, Any]:
    value = body.get("retention", "pending")
    if value not in {"object", "stone", "discard", "pending"}:
        raise HTTPException(422, "invalid_retention")
    cur = store.db.execute("UPDATE memories SET retention=? WHERE id=?", (value, memory_id)); store.db.commit()
    if cur.rowcount != 1:
        raise HTTPException(404, "memory_not_found")
    return {"memory": dict(store.db.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone())}
