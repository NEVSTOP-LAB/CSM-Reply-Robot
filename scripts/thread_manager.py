# -*- coding: utf-8 -*-
"""
对话线程管理器
==============

实施计划关联：AI-007 ThreadManager — 对话线程管理
参考文档：docs/调研/05-回复归档与存储.md

功能：
- 线程文件（thread.md）创建与读取
- 对话轮次追加（含真人回复 ⭐ 标记）
- 构建 OpenAI messages 格式的上下文
- YAML front-matter 管理

线程文件格式：
    ---
    thread_id: "12345678"
    article_id: "98765432"
    article_title: "CSM 最佳实践"
    commenter: "user_name"
    started_at: "2024-04-09T10:30:00"
    last_updated: "2024-04-09T11:15:00"
    turn_count: 3
    human_replied: false
    ---
    ## 对话记录
    ### 2024-04-09 10:30 · user_name（评论 #12345678）
    > 评论内容
    ### 2024-04-09 10:35 · Bot 回复（model: deepseek-chat, tokens: 150）
    回复内容
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import frontmatter

logger = logging.getLogger(__name__)


class ThreadManager:
    """对话线程管理器

    实施计划关联：AI-007

    管理 archive/articles/{article_id}/threads/ 下的线程文件，
    每个线程对应一个顶级评论及其所有追问。

    Args:
        archive_dir: 归档根目录路径
    """

    def __init__(self, archive_dir: str):
        self.archive_dir = Path(archive_dir)

    def _get_thread_dir(self, article_id: str) -> Path:
        """获取文章的线程目录"""
        thread_dir = self.archive_dir / "articles" / article_id / "threads"
        thread_dir.mkdir(parents=True, exist_ok=True)
        return thread_dir

    def get_or_create_thread(
        self,
        article_id: str,
        root_comment: dict,
        article_meta: dict,
    ) -> Path:
        """获取或创建线程文件

        实施计划关联：AI-007 任务 1

        如果线程已存在则返回路径，否则创建新线程文件。

        Args:
            article_id: 文章 ID
            root_comment: 顶级评论信息 {id, author, content, created_time}
            article_meta: 文章元信息 {title, url}

        Returns:
            线程文件路径
        """
        thread_dir = self._get_thread_dir(article_id)
        thread_id = str(root_comment["id"])
        thread_path = thread_dir / f"{thread_id}.md"

        if thread_path.exists():
            logger.debug(f"复用已有线程: {thread_path}")
            return thread_path

        # 创建新线程
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        metadata = {
            "thread_id": thread_id,
            "article_id": article_id,
            "article_title": article_meta.get("title", ""),
            "article_url": article_meta.get("url", ""),
            "commenter": root_comment.get("author", "unknown"),
            "started_at": now,
            "last_updated": now,
            "turn_count": 0,
            "human_replied": False,
        }

        content = "## 对话记录\n\n"
        post = frontmatter.Post(content, **metadata)

        with open(thread_path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))

        logger.info(f"创建新线程: {thread_path}")
        return thread_path

    def append_turn(
        self,
        thread_path: Path,
        author: str,
        content: str,
        is_human: bool = False,
        model: str | None = None,
        tokens: int | None = None,
    ):
        """追加对话轮次

        实施计划关联：AI-007 任务 2

        向线程文件追加一条对话记录。
        如果是真人回复（is_human=True），添加 ⭐ 标记并更新
        front-matter 中的 human_replied。

        Args:
            thread_path: 线程文件路径
            author: 发言者名称
            content: 发言内容
            is_human: 是否为真人回复
            model: Bot 使用的模型名称
            tokens: Bot 消耗的 token 数
        """
        post = frontmatter.load(str(thread_path))

        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 构建轮次标题
        if is_human:
            # 真人回复加 ⭐ 标记
            turn_header = f"### {now} · ⭐ {author}（真人回复）"
            post.metadata["human_replied"] = True
        elif model:
            turn_header = f"### {now} · Bot 回复（model: {model}, tokens: {tokens or 0}）"
        else:
            turn_header = f"### {now} · {author}"

        # 格式化内容
        if is_human or (not model):
            # 用户评论或真人回复使用引用格式
            formatted_content = "\n".join(
                f"> {line}" for line in content.split("\n")
            )
        else:
            # Bot 回复直接显示
            formatted_content = content

        turn_text = f"\n{turn_header}\n\n{formatted_content}\n"

        # 追加内容
        post.content = post.content.rstrip() + "\n" + turn_text

        # 更新 front-matter
        post.metadata["turn_count"] = post.metadata.get("turn_count", 0) + 1
        post.metadata["last_updated"] = datetime.now().strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        with open(thread_path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))

        logger.debug(
            f"追加轮次: {thread_path.name}, author={author}, "
            f"human={is_human}"
        )

    def build_context_messages(
        self,
        thread_path: Path,
        max_turns: int = 6,
    ) -> list[dict]:
        """构建 OpenAI messages 格式的上下文

        实施计划关联：AI-007 任务 3

        从线程文件中提取最近 max_turns 轮对话，
        转换为 OpenAI messages 格式（role + content）。

        Args:
            thread_path: 线程文件路径
            max_turns: 最多保留的轮次数

        Returns:
            OpenAI messages 格式的对话列表
        """
        post = frontmatter.load(str(thread_path))
        content = post.content

        # 解析对话轮次
        turns = self._parse_turns(content)

        # 截断到最近 max_turns 轮
        if len(turns) > max_turns:
            turns = turns[-max_turns:]

        # 转换为 messages 格式
        messages = []
        for turn in turns:
            role = self._determine_role(turn)
            messages.append({
                "role": role,
                "content": turn["content"],
            })

        return messages

    @staticmethod
    def _parse_turns(content: str) -> list[dict]:
        """解析线程内容中的对话轮次

        从 Markdown 内容中提取每个 ### 开头的轮次，
        解析出作者、类型和内容。

        Args:
            content: 线程文件的 Markdown 内容部分

        Returns:
            轮次列表，每个包含 header, content, is_bot, is_human
        """
        turns = []
        # 按 ### 分割
        sections = re.split(r'\n(?=###\s)', content)

        for section in sections:
            section = section.strip()
            if not section.startswith("###"):
                continue

            # 提取头部和内容
            lines = section.split("\n", 1)
            header = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ""

            # 移除引用符号
            body = re.sub(r'^>\s?', '', body, flags=re.MULTILINE).strip()

            is_bot = "Bot 回复" in header
            is_human = "⭐" in header or "真人回复" in header

            turns.append({
                "header": header,
                "content": body,
                "is_bot": is_bot,
                "is_human": is_human,
            })

        return turns

    @staticmethod
    def _determine_role(turn: dict) -> str:
        """确定轮次对应的 OpenAI message role

        Bot 回复 → "assistant"
        用户评论/真人回复 → "user"
        """
        if turn["is_bot"]:
            return "assistant"
        return "user"
