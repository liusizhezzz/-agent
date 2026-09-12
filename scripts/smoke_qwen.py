"""Live Qwen Omni protocol smoke test using WuWangWo's server configuration."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend_agent.config import load_settings
from backend_agent.qwen_adapter import QwenOmniRealtimeAdapter


async def main() -> None:
    settings = load_settings()
    adapter = QwenOmniRealtimeAdapter(settings, agent_id="light")
    await adapter.connect()
    setup = [json.loads(await adapter.ws.recv()).get("type") for _ in range(2)]
    await adapter.send({"type": "conversation.item.create", "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "今晚有点担心睡不着，我想先安静一会儿。"}]}})
    await adapter.send({"type": "response.create", "response": {"modalities": ["text"]}})
    events = []
    try:
        while len(events) < 30:
            event = json.loads(await asyncio.wait_for(adapter.ws.recv(), timeout=12))
            events.append(event.get("type"))
            if event.get("type") in {"response.text.done", "response.done", "error"}:
                break
    finally:
        await adapter.close()
    print(json.dumps({"qwen_ready": settings.qwen_ready, "setup_events": setup, "response_events": events, "passed": "response.created" in events}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
