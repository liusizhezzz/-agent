from __future__ import annotations

from .profiles import get_profile

BASE_SAFETY = """你服务于睡前陪伴场景。先共情理解，再给建议；不规训、不诊断、不承诺治疗或立即入睡，不制造依赖。用户回答变短、烦躁或说不想聊时减少提问，改为短句和可跳过选项。静默3至5秒先判断是在思考还是想结束；明确困倦、拒绝或结束时礼貌告别。只在Final ASR完成后触发RAG和正式回复；RAG超时使用基础角色Prompt，迟到结果不得补发第二条回复。"""


def compile_prompt(agent_id: str, *, user_text: str = "", rag: str = "") -> str:
    profile = get_profile(agent_id)
    parts = [BASE_SAFETY, f"你的身份是{profile['name']}，世界物件是“{profile['worldObject']}”。", f"人格：{profile['personality']}", f"CBT-I侧重点：{'、'.join(profile['cbtiFocus'])}", f"适用场景：{'、'.join(profile['适用场景'])}", f"说话方式：{profile['speechStyle']}", f"跟进规则：{'；'.join(profile['followUpRules'])}", f"静默规则：{profile['silencePolicy']}", f"告别规则：{profile['farewellRules']}", f"代表性话术：{profile['representativeLine']}"]
    parts.append(f"本轮RAG上下文（仅作参考）：{rag}" if rag else "本轮暂无RAG上下文。")
    if user_text:
        parts.append(f"用户当前表达：{user_text}")
    return "\n".join(parts)
