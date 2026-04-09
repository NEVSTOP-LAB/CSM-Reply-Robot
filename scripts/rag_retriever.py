"""
AI-005: RAGRetriever — CSM Wiki 增量 embedding + 检索
参考: docs/plan/README.md § AI-005, docs/调研/04-CSM-Wiki-RAG知识库.md

功能：
1. 本地 BGE embedding（BAAI/bge-small-zh-v1.5），支持线上 embedding 兜底
2. sync_wiki(force=False): MD5 比对增量更新，按标题分块
3. retrieve(query, k=3, threshold=0.72): reply_index top-2 优先 + wiki top-(k-2)
4. index_human_reply(question, reply, article_id, thread_id): 高权重写入 reply_index
5. 向量库使用 ChromaDB PersistentClient

设计说明：
- 增量更新通过 MD5 哈希比对，只处理变更文件
- reply_index 中真人回复权重高于 wiki 结果
- 向量库路径可配置（支持 Actions Cache 模式）
- embedding 支持本地/线上两种模式切换
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

import chromadb

logger = logging.getLogger(__name__)


class RAGRetriever:
    """
    CSM Wiki RAG 检索器
    参考: docs/plan/README.md § AI-005

    使用 ChromaDB 管理两个向量索引：
    - wiki_collection: CSM Wiki 文档索引
    - reply_collection: 历史回复索引（真人回复高权重）
    """

    # 默认配置
    DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
    DEFAULT_ONLINE_MODEL = "text-embedding-3-small"
    WIKI_COLLECTION_NAME = "csm_wiki"
    REPLY_COLLECTION_NAME = "reply_index"

    def __init__(
        self,
        wiki_dir: str,
        vector_store_dir: str,
        reply_index_dir: str,
        use_online_embedding: bool = False,
        wiki_hash_path: Optional[str] = None,
    ) -> None:
        """
        初始化 RAG 检索器

        Args:
            wiki_dir: CSM Wiki Markdown 文件目录
            vector_store_dir: Wiki 向量库持久化目录
            reply_index_dir: 回复索引持久化目录
            use_online_embedding: 是否使用线上 embedding（text-embedding-3-small）
            wiki_hash_path: wiki 文件哈希缓存路径（默认 data/wiki_hash.json）
        """
        self.wiki_dir = Path(wiki_dir)
        self.vector_store_dir = Path(vector_store_dir)
        self.reply_index_dir = Path(reply_index_dir)
        self.use_online_embedding = use_online_embedding
        self.wiki_hash_path = Path(wiki_hash_path) if wiki_hash_path else None

        # 初始化 embedding 函数
        self._embedding_fn = self._create_embedding_fn()

        # 初始化 ChromaDB
        # 参考: docs/调研/04-CSM-Wiki-RAG知识库.md § 3. 向量库选型
        self._init_chromadb()

        logger.info(
            "RAGRetriever 初始化完成: wiki_dir=%s, embedding=%s",
            self.wiki_dir,
            "online" if use_online_embedding else "local",
        )

    def _create_embedding_fn(self):
        """
        创建 embedding 函数
        参考: docs/plan/README.md § AI-005 第 1 点

        本地模式: BAAI/bge-small-zh-v1.5（sentence-transformers）
        线上模式: text-embedding-3-small（OpenAI API）
        """
        if self.use_online_embedding:
            return self._create_online_embedding_fn()
        else:
            return self._create_local_embedding_fn()

    def _create_local_embedding_fn(self):
        """创建本地 BGE embedding 函数"""
        try:
            from chromadb.utils import embedding_functions
            return embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.DEFAULT_EMBEDDING_MODEL,
            )
        except ImportError:
            logger.warning("sentence-transformers 未安装，尝试线上 embedding")
            return self._create_online_embedding_fn()

    def _create_online_embedding_fn(self):
        """
        创建线上 embedding 函数（OpenAI text-embedding-3-small）
        参考: docs/plan/README.md § AI-005 第 1 点 — use_online_embedding 开关
        """
        try:
            from chromadb.utils import embedding_functions
            api_key = os.environ.get("OPENAI_API_KEY", os.environ.get("LLM_API_KEY", ""))
            return embedding_functions.OpenAIEmbeddingFunction(
                api_key=api_key,
                model_name=self.DEFAULT_ONLINE_MODEL,
            )
        except Exception as e:
            logger.error("无法创建线上 embedding: %s", e)
            raise

    def _init_chromadb(self) -> None:
        """
        初始化 ChromaDB PersistentClient
        参考: docs/调研/04-CSM-Wiki-RAG知识库.md § 3. 向量库选型
        """
        # Wiki 向量库
        self.vector_store_dir.mkdir(parents=True, exist_ok=True)
        self._wiki_client = chromadb.PersistentClient(
            path=str(self.vector_store_dir)
        )
        self.wiki_collection = self._wiki_client.get_or_create_collection(
            name=self.WIKI_COLLECTION_NAME,
            embedding_function=self._embedding_fn,
        )

        # 回复索引向量库
        self.reply_index_dir.mkdir(parents=True, exist_ok=True)
        self._reply_client = chromadb.PersistentClient(
            path=str(self.reply_index_dir)
        )
        self.reply_collection = self._reply_client.get_or_create_collection(
            name=self.REPLY_COLLECTION_NAME,
            embedding_function=self._embedding_fn,
        )

    def sync_wiki(self, force: bool = False) -> int:
        """
        增量同步 CSM Wiki 到向量库
        参考: docs/plan/README.md § AI-005 第 2 点, docs/调研/04-CSM-Wiki-RAG知识库.md § 6. 增量更新机制

        通过 MD5 哈希比对，只对变更文件重新 embedding。

        Args:
            force: 是否强制全量重建

        Returns:
            更新的文件数量
        """
        # 加载旧哈希
        old_hashes = self._load_hashes()
        new_hashes: dict[str, str] = {}
        updated_count = 0

        # 扫描所有 Markdown 文件
        md_files = list(self.wiki_dir.glob("**/*.md"))
        logger.info("扫描 Wiki 目录: %s，找到 %d 个 Markdown 文件", self.wiki_dir, len(md_files))

        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            file_key = str(md_file.relative_to(self.wiki_dir))
            file_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
            new_hashes[file_key] = file_hash

            # 判断是否需要更新
            if not force and old_hashes.get(file_key) == file_hash:
                logger.debug("文件未变更，跳过: %s", file_key)
                continue

            # 删除旧向量
            # 参考: docs/调研/04-CSM-Wiki-RAG知识库.md § 6. 增量更新机制
            try:
                self.wiki_collection.delete(where={"source": file_key})
            except Exception:
                pass  # 首次没有旧数据

            # 分块并添加新向量
            chunks = self._chunk_markdown(content, file_key)
            if chunks:
                ids = [f"{file_key}_{i}" for i in range(len(chunks))]
                documents = [c["text"] for c in chunks]
                metadatas = [{"source": c["source"], "title": c.get("title", "")} for c in chunks]
                self.wiki_collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                )
                logger.info("更新 Wiki 索引: %s（%d 个分块）", file_key, len(chunks))
                updated_count += 1

        # 处理已删除的文件
        deleted_files = set(old_hashes.keys()) - set(new_hashes.keys())
        for deleted_key in deleted_files:
            try:
                self.wiki_collection.delete(where={"source": deleted_key})
                logger.info("删除已移除文件的索引: %s", deleted_key)
            except Exception:
                pass

        # 保存新哈希
        self._save_hashes(new_hashes)

        logger.info("Wiki 同步完成: %d 个文件更新", updated_count)
        return updated_count

    @staticmethod
    def _chunk_markdown(text: str, source: str) -> list[dict]:
        """
        按 Markdown 标题分块
        参考: docs/调研/04-CSM-Wiki-RAG知识库.md § 5. 文档分块策略

        每块约 300~500 tokens，带标题前缀用于上下文溯源。

        Args:
            text: Markdown 文本
            source: 来源文件名

        Returns:
            分块列表，每块含 text, source, title
        """
        # 按 # 标题边界分割
        sections = re.split(r'\n(?=#{1,3} )', text)
        chunks = []
        for section in sections:
            stripped = section.strip()
            if not stripped:
                continue

            # 提取标题
            title_match = re.match(r'^(#{1,3})\s+(.+)', stripped)
            title = title_match.group(2) if title_match else ""

            chunks.append({
                "text": stripped,
                "source": source,
                "title": title,
            })

        return chunks

    def retrieve(
        self,
        query: str,
        k: int = 3,
        threshold: float = 0.72,
    ) -> list[str]:
        """
        检索与 query 相关的内容
        参考: docs/plan/README.md § AI-005 第 3 点

        策略：先 reply_index top-2，再 wiki top-(k-2)
        reply_index 中真人回复优先（高权重）

        Args:
            query: 查询文本
            k: 返回最多 k 个结果
            threshold: 相似度阈值（低于此值的结果被过滤）

        Returns:
            相关文本片段列表
        """
        results: list[str] = []

        # 1. 从 reply_index 检索（优先，最多 2 条）
        # 参考: docs/调研/05-回复归档与存储.md § 6. 人工回复的权重机制
        reply_k = min(2, k)
        try:
            reply_results = self.reply_collection.query(
                query_texts=[query],
                n_results=reply_k,
                where={"weight": "high"},
            )
            if reply_results and reply_results["documents"]:
                for doc_list, dist_list in zip(
                    reply_results["documents"],
                    reply_results.get("distances", [[]]),
                ):
                    for doc, dist in zip(doc_list, dist_list):
                        # ChromaDB 距离越小越相似（L2距离）
                        # 转换为相似度：similarity = 1 / (1 + distance)
                        similarity = 1.0 / (1.0 + dist)
                        if similarity >= threshold:
                            results.append(doc)
        except Exception as e:
            logger.debug("reply_index 检索失败（可能为空）: %s", e)

        # 2. 从 wiki 检索补充（剩余名额）
        wiki_k = k - len(results)
        if wiki_k > 0:
            try:
                wiki_results = self.wiki_collection.query(
                    query_texts=[query],
                    n_results=wiki_k,
                )
                if wiki_results and wiki_results["documents"]:
                    for doc_list, dist_list in zip(
                        wiki_results["documents"],
                        wiki_results.get("distances", [[]]),
                    ):
                        for doc, dist in zip(doc_list, dist_list):
                            similarity = 1.0 / (1.0 + dist)
                            if similarity >= threshold:
                                results.append(doc)
            except Exception as e:
                logger.debug("wiki 检索失败（可能为空）: %s", e)

        logger.info("RAG 检索完成: query=%s..., 返回 %d 条", query[:30], len(results))
        return results

    def index_human_reply(
        self,
        question: str,
        reply: str,
        article_id: str,
        thread_id: str,
    ) -> None:
        """
        将真人回复以高权重写入 reply_index
        参考: docs/plan/README.md § AI-005 第 4 点, docs/调研/05-回复归档与存储.md § 6. 人工回复的权重机制

        Args:
            question: 用户问题
            reply: 真人回复内容
            article_id: 文章 ID
            thread_id: 线程 ID
        """
        doc_id = f"human_{article_id}_{thread_id}"
        document = f"[问题] {question}\n[作者回复] {reply}"
        metadata = {
            "source": "human_reply",
            "weight": "high",
            "article_id": article_id,
            "thread_id": thread_id,
        }

        # 先删除旧的（如果存在）
        try:
            self.reply_collection.delete(ids=[doc_id])
        except Exception:
            pass

        self.reply_collection.add(
            ids=[doc_id],
            documents=[document],
            metadatas=[metadata],
        )

        logger.info(
            "索引真人回复: article=%s, thread=%s, weight=high",
            article_id, thread_id,
        )

    def _load_hashes(self) -> dict[str, str]:
        """加载 Wiki 文件哈希缓存"""
        if self.wiki_hash_path and self.wiki_hash_path.exists():
            with open(self.wiki_hash_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_hashes(self, hashes: dict[str, str]) -> None:
        """保存 Wiki 文件哈希缓存"""
        if self.wiki_hash_path:
            self.wiki_hash_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.wiki_hash_path, "w", encoding="utf-8") as f:
                json.dump(hashes, f, ensure_ascii=False, indent=2)
