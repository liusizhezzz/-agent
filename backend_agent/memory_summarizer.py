from __future__ import annotations

import asyncio
import json
import urllib.request

from .config import Settings


class MemorySummarizer:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def summarize(self, transcript: str, fallback: str) -> tuple[str, str]:
        if not self.settings.api_key or not transcript.strip():
            return fallback, "fallback"
        return await asyncio.to_thread(self._request, transcript, fallback)

    def _request(self, transcript: str, fallback: str) -> tuple[str, str]:
        payload = {"model": self.settings.qwen_max_model, "input": {"messages": [{"role": "system", "content": "将睡前陪伴对话总结成一句温和、客观、不诊断的中文记忆摘要。只输出摘要。"}, {"role": "user", "content": transcript[-12000:]}]}}
        req = urllib.request.Request("https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation", data=json.dumps(payload, ensure_ascii=False).encode(), headers={"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read())
            text = data.get("output", {}).get("text", "").strip()
            return (text[:500] or fallback), "qwen-max"
        except Exception:
            return fallback, "fallback_timeout"
