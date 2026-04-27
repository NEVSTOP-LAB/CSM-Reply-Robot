"""数据类型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True)
class Message:
    """多轮对话历史中的一条消息。

    Attributes:
        role: 角色，``"user"`` / ``"assistant"`` / ``"system"`` 之一。
        content: 消息文本。
    """

    role: Role
    content: str

    def to_openai(self) -> dict:
        """转换为 OpenAI Chat Completion 的 ``messages`` 元素格式。"""
        return {"role": self.role, "content": self.content}


@dataclass
class Usage:
    """单次 LLM 调用的 token 用量。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class AnswerResult:
    """:meth:`CSMQa.ask_detailed` 的返回类型。

    Attributes:
        answer: 模型生成的回答文本。
        contexts: 本次回答使用的 RAG 检索片段（按相关度排序）。
        usage: token 使用统计。
        model: 实际使用的模型名。
        prompt_messages: 实际发送给模型的完整 messages 列表（调试用）。
    """

    answer: str
    contexts: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    prompt_messages: list[dict] = field(default_factory=list)
