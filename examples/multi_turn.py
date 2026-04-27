"""多轮对话 + 自定义参数示例。"""

from __future__ import annotations

from csm_qa import CSM_QA, Message


def main() -> None:
    qa = CSM_QA(
        api_key="sk-xxx",                    # 替换为你的 key
        provider="deepseek",                 # 或 "openai_compatible"
        model="deepseek-chat",
        temperature=0.3,
        top_k=4,
    )

    history = [
        Message(role="user", content="CSM 是什么？"),
        Message(
            role="assistant",
            content="CSM 是 Communicable State Machine，一种基于消息通信的状态机框架。",
        ),
    ]

    result = qa.ask_detailed(
        "那它和 JKI SM 有什么区别？",
        history=history,
    )
    print("回答：", result.answer)
    print("使用的片段数：", len(result.contexts))
    print("token 用量：", result.usage)


if __name__ == "__main__":
    main()
