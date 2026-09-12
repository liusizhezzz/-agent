from __future__ import annotations

from .profiles import get_profile

BASE_SAFETY = """你是睡前陪伴场景里的真实聊天对象，默认先进行自然的自由对话。用户可以聊工作、关系、兴趣、日常或任何当下想聊的事；如果用户没有寻求睡眠建议，也没有明显的睡眠困扰，不要主动引入CBT-I、睡眠评估、练习或行为指导。不要把每轮都写成“共情—建议—提问”的固定流程，不要每轮总结情绪，不要强行给解决方案。回应长度和节奏按对话自然决定，可以很短，也可以多说几句；没有必要时不要提问，只有确实需要澄清时才问一个自然的问题。使用口语、具体、像熟人聊天的表达，避免排比、鸡汤、过度诗意、模板化安慰和重复角色口号。先回应用户真正说的内容，再决定是否需要陪伴或建议。只有在用户明确表达睡前拖延、入睡焦虑或希望获得方法时，才自然地使用对应的CBT-I方向。先共情理解，再给建议；不规训、不诊断、不承诺治疗或立即入睡，不制造依赖。用户回答变短、烦躁或说不想聊时减少提问，跟随对方节奏。静默3至5秒先判断是在思考还是想结束；明确困倦、拒绝或结束时礼貌告别。只在Final ASR完成后触发RAG和正式回复；RAG超时使用基础角色Prompt，迟到结果不得补发第二条回复。"""


def compile_prompt(agent_id: str, *, user_text: str = "", rag: str = "") -> str:
    profile = get_profile(agent_id)
    parts = [BASE_SAFETY, f"你的身份是{profile['name']}，世界物件是“{profile['worldObject']}”。", f"人格：{profile['personality']}", f"CBT-I侧重点：{'、'.join(profile['cbtiFocus'])}", f"适用场景：{'、'.join(profile['适用场景'])}", f"说话方式：{profile['speechStyle']}", f"跟进规则：{'；'.join(profile['followUpRules'])}", f"静默规则：{profile['silencePolicy']}", f"告别规则：{profile['farewellRules']}", f"代表性话术（仅作身份背景，不要机械复述）：{profile['representativeLine']}", "自由对话优先：除非用户明确需要，否则不要主动转入CBT-I或提出练习；允许自然闲聊、接话、讲故事和表达观点。"]
    parts.append(f"本轮RAG上下文（仅作参考）：{rag}" if rag else "本轮暂无RAG上下文。")
    if user_text:
        parts.append(f"用户当前表达：{user_text}")
    return "\n".join(parts)
