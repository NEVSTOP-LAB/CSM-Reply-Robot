"""Prompt 模板测试。"""

from csm_qa.prompts import (
    CONTEXT_BLOCK_TEMPLATE,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_WIKI_BASE_URL,
    build_system_message,
)


def test_default_system_prompt_mentions_csm():
    assert "CSM" in DEFAULT_SYSTEM_PROMPT
    assert "LabVIEW" in DEFAULT_SYSTEM_PROMPT


def test_default_system_prompt_requires_wiki_links():
    """默认提示词应要求把关键信息写成指向 csm-wiki 的 Markdown 超链接。"""
    assert "Markdown" in DEFAULT_SYSTEM_PROMPT
    assert "链接" in DEFAULT_SYSTEM_PROMPT
    assert "csm-wiki" in DEFAULT_SYSTEM_PROMPT


def test_default_wiki_base_url_points_to_csm_wiki_repo():
    assert DEFAULT_WIKI_BASE_URL.startswith("https://")
    assert "CSM-Wiki" in DEFAULT_WIKI_BASE_URL


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


def test_build_system_message_with_metadata_includes_wiki_link():
    """传入带 source 的 dict 时，应把 source 拼成指向 csm-wiki 的链接。"""
    contexts = [
        {"text": "正文A", "source": "guide/intro.md", "heading": "概述"},
        {"text": "正文B", "source": "api/state.md", "heading": "Untitled"},
    ]
    out = build_system_message(DEFAULT_SYSTEM_PROMPT, contexts)
    assert "正文A" in out and "正文B" in out
    assert "来源: guide/intro.md" in out
    assert "小节: 概述" in out
    # Untitled 不显示
    assert "小节: Untitled" not in out
    # 链接以默认 wiki base url 拼接
    assert f"{DEFAULT_WIKI_BASE_URL}/guide/intro.md" in out
    assert f"{DEFAULT_WIKI_BASE_URL}/api/state.md" in out


def test_build_system_message_with_custom_wiki_base_url():
    contexts = [{"text": "x", "source": "foo.md", "heading": "H"}]
    out = build_system_message(
        DEFAULT_SYSTEM_PROMPT, contexts, wiki_base_url="https://wiki.example.com/docs"
    )
    assert "https://wiki.example.com/docs/foo.md" in out


def test_build_system_message_handles_missing_metadata_fields():
    """source/heading 为空或缺失时不应抛错，且不应输出空的 ``来源:``/``小节:`` 行。"""
    contexts = [
        {"text": "无元数据", "source": "", "heading": ""},
        {"text": "仅 source", "source": "only_src.md"},
    ]
    out = build_system_message(DEFAULT_SYSTEM_PROMPT, contexts)
    assert "无元数据" in out
    assert "仅 source" in out
    # 没有 source 时不应出现空 "来源: " 行；也不应生成空链接
    assert "来源: \n" not in out and "来源:  " not in out
    assert "链接: \n" not in out
    # 有 source 时应正常拼链接
    assert f"{DEFAULT_WIKI_BASE_URL}/only_src.md" in out


def test_build_system_message_treats_unknown_source_as_missing():
    """``(unknown)`` 占位符应被视为缺失，不输出 ``来源:`` 行也不生成链接。"""
    contexts = [{"text": "正文", "source": "(unknown)", "heading": "H"}]
    out = build_system_message(DEFAULT_SYSTEM_PROMPT, contexts)
    # 仅检查参考资料段（系统提示词本身含有 "来源"/"链接" 等关键字）
    ctx_section = out.split("【参考资料】", 1)[1]
    assert "正文" in ctx_section
    assert "(unknown)" not in ctx_section
    assert "来源:" not in ctx_section
    assert "链接:" not in ctx_section


def test_build_system_message_empty_base_url_skips_link():
    """``wiki_base_url`` 为空/空白时不应生成形如 ``/foo.md`` 的无效链接。"""
    contexts = [{"text": "x", "source": "foo.md", "heading": "H"}]
    out = build_system_message(DEFAULT_SYSTEM_PROMPT, contexts, wiki_base_url="   ")
    ctx_section = out.split("【参考资料】", 1)[1]
    assert "x" in ctx_section
    assert "来源: foo.md" in ctx_section
    # 不应出现链接行，也不应注入相对路径式的 "/foo.md"
    assert "链接:" not in ctx_section
    assert "/foo.md" not in ctx_section


def test_context_block_template_structure():
    # 模板必须包含 {contexts} 占位符，以便上层注入
    assert "{contexts}" in CONTEXT_BLOCK_TEMPLATE
