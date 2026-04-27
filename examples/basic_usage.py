"""最简单的单轮问答示例。

运行前：
    export LLM_API_KEY=sk-xxx
    pip install -e .
"""

from __future__ import annotations

from csm_qa import CSMQa


def main() -> None:
    qa = CSMQa.from_env()  # 自动读取 LLM_API_KEY
    answer = qa.ask("CSM 框架中的状态机是怎么切换的？")
    print(answer)


if __name__ == "__main__":
    main()
