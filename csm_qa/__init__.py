"""csm_qa — 通用 RAG 问答库

对外只暴露三个核心符号：

- :class:`CSM_QA`：主入口类，封装 RAG 检索 + LLM 调用
- :class:`Message`：多轮对话历史的不可变数据载体
- :class:`AnswerResult`：``ask_detailed`` 的返回类型

最简用法::

    from csm_qa import CSM_QA

    qa = CSM_QA(api_key="sk-xxx")          # 默认 deepseek
    answer = qa.ask("CSM 的状态机如何切换？")
"""

from csm_qa.api import CSM_QA
from csm_qa.types import AnswerResult, Message

__all__ = ["CSM_QA", "Message", "AnswerResult"]
__version__ = "0.1.0"
