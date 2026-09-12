from __future__ import annotations

from .profiles import PROFILES

SIGNALS = {
    "fox": ("刷短视频", "报复性", "舍不得结束", "属于我的时间", "停不下来"),
    "plant": ("仪式", "放松", "切换", "兴奋", "房间", "洗澡"),
    "soil": ("待办", "明天", "盘算", "没做完", "脑子", "工作", "担心"),
    "light": ("睡不着", "害怕躺下", "盯着时间", "越努力", "失眠", "焦虑入睡"),
}


def recommend(text: str) -> dict:
    ranked = []
    for profile in PROFILES:
        score = sum(text.count(word) for word in SIGNALS.get(profile["id"], ()))
        ranked.append((score, profile))
    ranked.sort(key=lambda item: item[0], reverse=True)
    score, winner = ranked[0]
    hit = next((word for word in SIGNALS[winner["id"]] if word in text), None)
    reason = f"你提到“{hit}”，今晚更适合从{winner['worldObject']}开始。" if hit else "今晚先从最稳的土壤开始；你仍可以随时切换。"
    return {"agent": winner, "reason": reason, "scores": [{"id": p["id"], "score": s} for s, p in ranked]}
