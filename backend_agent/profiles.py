from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PROFILES: list[dict[str, Any]] = json.loads((ROOT / "agent_profiles.json").read_text(encoding="utf-8"))
BY_ID = {profile["id"]: profile for profile in PROFILES}


def get_profile(agent_id: str) -> dict[str, Any]:
    return BY_ID.get(agent_id, BY_ID["soil"])
