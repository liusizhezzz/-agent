"""Qwen Omni realtime WebSocket adapter.

This is a project-local adapter based on the upstream fun-audiochat-realtime
protocol. It keeps DashScope credentials server-side and forwards the same
event stream between browser and Qwen Omni. Without credentials it returns a
structured error so the UI can remain in text/demo mode.
"""
import asyncio
import json
import os
import base64
from urllib.parse import parse_qs, urlparse

import websockets

BASE_URL = os.getenv("FUN_REALTIME_BASE_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime")
MODEL = os.getenv("FUN_REALTIME_MODEL", "qwen-omni-turbo-realtime")
SPACE_ID = os.getenv("FUN_REALTIME_SPACE_ID", "")
API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
PORT = int(os.getenv("QWEN_WS_PORT", "8181"))


def _prompt(agent_id: str) -> str:
    """Load the compiled role prompt through the Node registry contract."""
    try:
        with open(os.path.join(os.path.dirname(__file__), "..", "agent_profiles.json"), encoding="utf-8") as f:
            profiles = json.load(f)
        profile = next((p for p in profiles if p["id"] == agent_id), profiles[0])
        return (f"你是{profile['name']}，世界物件是{profile['worldObject']}。"
                f"人格：{profile['personality']} CBT-I重点：{'、'.join(profile['cbtiFocus'])}。"
                f"说话方式：{profile['speechStyle']} 先共情再建议，不诊断、不承诺立即入睡。")
    except Exception:
        return "你是睡前陪伴 Agent，先共情再建议，保持短句和低刺激语气。"


async def proxy(browser):
    query = parse_qs(urlparse(browser.request.path).query)
    agent_id = query.get("agent", ["soil"])[0]
    if not API_KEY or not SPACE_ID:
        await browser.send(json.dumps({"type": "error", "error": {"code": "QWEN_CONFIG_MISSING", "message": "请在服务端设置 DASHSCOPE_API_KEY 与 FUN_REALTIME_SPACE_ID"}}, ensure_ascii=False))
        return
    upstream = f"{BASE_URL}?model={query.get('model', [MODEL])[0]}"
    headers = {"Authorization": f"Bearer {API_KEY}", "X-DashScope-Space": SPACE_ID}
    try:
        async with websockets.connect(upstream, additional_headers=headers, max_size=None) as qwen:
            await qwen.send(json.dumps({"type": "session.update", "session": {"instructions": _prompt(agent_id), "turn_detection": {"type": "server_vad", "silence_duration_ms": 3500}}}, ensure_ascii=False))

            async def forward_in():
                async for message in browser:
                    if isinstance(message, bytes):
                        message = json.dumps({"type": "input_audio_buffer.append", "audio": base64.b64encode(message).decode()})
                    await qwen.send(message)

            async def forward_out():
                async for message in qwen:
                    await browser.send(message)

            await asyncio.gather(forward_in(), forward_out())
    except websockets.exceptions.ConnectionClosed:
        return
    except Exception as exc:
        await browser.send(json.dumps({"type": "error", "error": {"code": "QWEN_PROXY_ERROR", "message": str(exc)[:240]}}, ensure_ascii=False))


async def main():
    async with websockets.serve(proxy, "0.0.0.0", PORT, max_size=None):
        print(f"Qwen Omni adapter listening on ws://localhost:{PORT}/ws")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
