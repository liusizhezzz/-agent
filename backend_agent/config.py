from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


@dataclass(frozen=True)
class Settings:
    api_key: str
    space_id: str
    model: str
    base_url: str
    qwen_max_model: str
    db_path: Path
    host: str = "0.0.0.0"
    port: int = 8180

    @property
    def qwen_ready(self) -> bool:
        # WuWangWo's existing Omni client authenticates with DASHSCOPE_API_KEY;
        # Space ID remains an optional deployment override.
        return bool(self.api_key and self.model)


def load_settings() -> Settings:
    # Local development may reuse WuWangWo's existing secret file. Production
    # should set WUWANGWO_ENV_FILE or inject the variables through systemd/K8s.
    candidate = os.getenv("WUWANGWO_ENV_FILE", "")
    if not candidate:
        candidate = "/Users/cls/Desktop/勿忘我项目开发板/forget-me-not-ad-screening/backend/.env.local"
    file_values = _load_env_file(Path(candidate))

    def value(*names: str, default: str = "") -> str:
        for name in names:
            if os.getenv(name):
                return os.environ[name]
            if file_values.get(name):
                return file_values[name]
        return default

    return Settings(
        api_key=value("DASHSCOPE_API_KEY"),
        space_id=value("FUN_REALTIME_SPACE_ID", "DASHSCOPE_SPACE_ID"),
        model=value("FUN_REALTIME_MODEL", "DASHSCOPE_OMNI_REALTIME_MODEL", "DASHSCOPE_OMNI_MODEL", default="qwen3.5-omni-flash-realtime"),
        base_url=value("FUN_REALTIME_BASE_URL", default="wss://dashscope.aliyuncs.com/api-ws/v1/realtime"),
        qwen_max_model=value("QWEN_MAX_MODEL", default="qwen-max"),
        db_path=Path(value("AGENT_DB_PATH", default="data/agent.sqlite")),
        host=value("AGENT_HOST", default="0.0.0.0"),
        port=int(value("AGENT_PORT", default="8180")),
    )
