"""Prompt 模板测试。"""

from csm_qa.prompts import (
    CONTEXT_BLOCK_TEMPLATE,
    DEFAULT_SYSTEM_PROMPT,
    build_system_message,
)


def test_default_system_prompt_mentions_csm():
    assert "CSM" in DEFAULT_SYSTEM_PROMPT
    assert "LabVIEW" in DEFAULT_SYSTEM_PROMPT


def test_build_system_message_with_contexts():
    out = build_system_message(
        DEFAULT_SYSTEM_PROMPT, ["片段A", "片段B"]
    )
    assert out.startswith(DEFAULT_SYSTEM_PROMPT)
    assert "[片段 1]" in out
    assert "片段A" in out
    assert "[片段 2]" in out
    assert "片段B" in out


def test_build_system_message_empty_contexts():
    out = build_system_message(DEFAULT_SYSTEM_PROMPT, [])
    # 没有片段时应显示"（无）"占位，避免模型困惑
    assert "（无）" in out


def test_context_block_template_structure():
    # 模板必须包含 {contexts} 占位符，以便上层注入
    assert "{contexts}" in CONTEXT_BLOCK_TEMPLATE
