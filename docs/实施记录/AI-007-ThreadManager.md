# AI-007 实施记录：ThreadManager — 对话线程管理

## 状态：✅ 完成

## 实施内容

### ThreadManager 类实现 (`scripts/thread_manager.py`)
- `get_or_create_thread(article_id, root_comment, article_meta)` → Path
  - 新建 thread.md 含 YAML front-matter（thread_id, article_id, commenter 等）
  - 已有线程直接返回路径
- `append_turn(thread_path, author, content, is_human, model, tokens)`
  - is_human=True 添加 ⭐ 标记，更新 human_replied=true
  - Bot 回复记录 model 和 tokens
  - 自动递增 turn_count，更新 last_updated
- `build_context_messages(thread_path, max_turns=6)` → list[dict]
  - OpenAI messages 格式（role: user/assistant）
  - 超 max_turns 时截断为最近轮次
  - Bot 回复 → assistant，用户/真人 → user

### 线程文件格式
使用 python-frontmatter 管理 YAML 元数据 + Markdown 内容

## 测试结果
```
19 passed in 0.09s
```

覆盖：线程创建（5）、轮次追加（7）、上下文构建（7）

## 验收标准
- [x] 顶级评论新建 thread，追问复用已有 thread
- [x] append_turn 后 front-matter 可正确解析
- [x] is_human=True 时 ⭐ 存在
- [x] build_context_messages 超 max_turns 截断
