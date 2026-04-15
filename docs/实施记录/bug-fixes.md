# Bug Fixes 记录

本文档记录代码 review 中发现的 bug 及其修复方案，修复日期 2026-04-12。

---

## BUG-FIX-01 — `_handle_human_reply` 真人回复问题提取错误（根源修复）

### 问题位置
`scripts/thread_manager.py::ThreadManager::_parse_turns`
`scripts/run_bot.py::BotRunner::_handle_human_reply`

### 现象
当知乎文章作者手动回复用户评论时（`is_author_reply=True`），Bot 会将该 QA 对
索引到 RAG 的 reply_index 以实现"自学习"。但索引的 `question` 字段取的是
**作者自己的回复内容**，而非**用户的原始提问**，导致 RAG 检索效果为零。

### 根本原因
`_parse_turns` 在识别消息角色时，原有判断标准为：

```python
is_bot = "Bot 回复" in section or "机器人回复" in section
```

真人回复的标题含"真人回复（作者本人）⭐"，不含以上关键词，因此被识别为
`is_bot=False`，映射为 `"user"` 角色。

因此 `_handle_human_reply` 中 `reversed(messages)` 找到的第一条 `"user"` 消息
可能是**历史中任意一条真人回复**（若作者曾多次手动回复），而非用户的提问。

### 修复方案（根源修复）
在 `_parse_turns` 中将"真人回复"纳入 `is_bot=True` 的判断条件：

```python
is_bot = (
    "Bot 回复" in section
    or "机器人回复" in section
    or "真人回复" in section   # ← 新增：作者真人回复同属"回答方"
)
```

这样"真人回复"在 `build_context_messages` 中被映射为 `role="assistant"`，
`reversed(messages)` 会跳过所有 assistant 消息，只取用户的提问内容。

**语义正确性**：在 LLM 对话上下文中，Bot 回复和作者真人回复都属于"回答方"，
映射为 `assistant` role 更符合 OpenAI messages 格式的语义。

### 测试覆盖
- 更新 `test_thread_manager.py::test_human_reply_is_assistant_role`（原 `test_human_reply_is_user_role`）
- 更新 `test_run_bot.py::TestHumanReplyQuestion::test_human_reply_question_not_self_indexed`
- 新增 `test_run_bot.py::TestHumanReplyQuestion::test_prior_human_reply_not_mistaken_as_question`（多轮真人回复场景）

---

## BUG-FIX-02 — `_write_pending` YAML frontmatter 双引号注入

### 问题位置
`scripts/run_bot.py::BotRunner::_write_pending`

### 现象
当 `risk_reason`（来自 LLM 的 `assess_risk` 返回值）或 `article_title`
（来自 API/配置）包含双引号 `"` 时，手动拼接生成的 YAML frontmatter 格式
非法，`approve_pending` 中的 `frontmatter.load()` 会抛出 `YAMLError`，
导致审核操作静默失败（异常被 `except Exception` 捕获后返回 `False`）。

### 复现示例
```yaml
# 非法 YAML（risk_reason 含双引号时）
risk_reason: "包含 "双引号" 的理由"
```
`yaml.safe_load` 对此抛出 `YAMLError`。

### 修复方案
将 frontmatter 字段改为通过 `yaml.dump` 生成，利用 PyYAML 自动处理特殊字符：

```python
meta = {
    "article_id": article["id"],
    "article_title": article.get("title", ""),
    ...
    "risk_reason": risk_reason,
}
meta_yaml = yaml.dump(meta, allow_unicode=True, default_flow_style=False)
content = f"---\n{meta_yaml}---\n\n## 原始评论\n\n..."
```

### 测试覆盖
新增 `TestWritePending::test_pending_yaml_safe_with_quotes_in_risk_reason`，
验证含双引号的 `risk_reason` 生成的文件仍可被 `frontmatter.load` 正常解析。

---

## BUG-FIX-03 — `test_article_type_valid` 测试断言过期

### 问题位置
`tests/test_config.py::TestArticlesConfig::test_article_type_valid`

### 现象
测试检查 `articles.yaml` 中所有条目的 `type` 字段，但只认可
`{"article", "question"}` 两种类型。而 `articles.yaml` 实际包含
`"column"` 和 `"user_answers"` 类型，且 `_expand_articles()` 已支持这两种
类型的展开，导致本测试始终失败（预先存在的失败项）。

### 修复方案
将 `valid_types` 更新为与 `_expand_articles` 实现保持一致的完整集合：

```python
valid_types = {"article", "question", "column", "user_answers", "answer"}
```

### 影响说明
此为测试代码修复，不影响运行时逻辑。
