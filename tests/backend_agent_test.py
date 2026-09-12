import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend_agent.config import load_settings
from backend_agent.matcher import recommend
from backend_agent.prompts import compile_prompt
from backend_agent.store import Store


def main():
    assert load_settings().api_key, "WuWangWo DASHSCOPE_API_KEY was not loaded"
    assert recommend("我一直盘算明天没做完的待办")["agent"]["id"] == "soil"
    prompt = compile_prompt("light", user_text="越努力越睡不着")
    for term in ("澄", "入睡焦虑", "不诊断", "Final ASR", "RAG"):
        assert term in prompt
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "agent.sqlite")
        session = store.create_session("plant", "rain")
        assert store.session_agent(session) == "plant"
        memory = store.end_session(session, "plant", "一片叶子", "今晚想慢下来", "今晚想慢下来。", "睡眠体验", "stone")
        assert memory["retention"] == "stone"
    print("backend agent checks passed")


if __name__ == "__main__":
    main()
