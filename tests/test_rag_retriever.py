"""
AI-005: RAGRetriever 单元测试
参考: docs/plan/README.md § AI-005 测试要求

测试覆盖：
- sync_wiki 只对变更文件重新 embedding（mock MD5 变化）
- retrieve 相似度阈值过滤
- retrieve 优先返回 reply_index 中高权重结果
- index_human_reply 高权重元数据
- use_online_embedding 开关
- Markdown 分块逻辑

注意：所有测试使用 Mock ChromaDB，不依赖真实的 embedding 模型或 ChromaDB 实例。
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ─── 辅助 fixtures ──────────────────────────────────────────────

@pytest.fixture
def wiki_dir(tmp_path: Path) -> Path:
    """创建临时 wiki 目录"""
    wiki = tmp_path / "csm-wiki"
    wiki.mkdir()
    return wiki


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """创建临时数据目录"""
    d = tmp_path / "data"
    d.mkdir()
    (d / "vector_store").mkdir()
    (d / "reply_index").mkdir()
    return d


@pytest.fixture
def wiki_hash_path(data_dir: Path) -> Path:
    """wiki hash 文件路径"""
    p = data_dir / "wiki_hash.json"
    p.write_text("{}", encoding="utf-8")
    return p


def create_mock_collection():
    """创建 mock ChromaDB collection"""
    mock = MagicMock()
    mock.add = MagicMock()
    mock.delete = MagicMock()
    mock.query = MagicMock(return_value={
        "documents": [[]],
        "distances": [[]],
        "metadatas": [[]],
    })
    mock.count = MagicMock(return_value=0)
    return mock


@pytest.fixture
def mock_chromadb():
    """Mock chromadb 模块 — 在 rag_retriever 模块中 patch chromadb.PersistentClient"""
    mock_wiki_collection = create_mock_collection()
    mock_reply_collection = create_mock_collection()

    mock_client = MagicMock()

    # get_or_create_collection 按名称返回不同的 collection
    def get_or_create_collection(name, **kwargs):
        if "wiki" in name:
            return mock_wiki_collection
        else:
            return mock_reply_collection

    mock_client.get_or_create_collection = MagicMock(side_effect=get_or_create_collection)

    with patch("chromadb.PersistentClient", return_value=mock_client):
        yield {
            "client": mock_client,
            "wiki_collection": mock_wiki_collection,
            "reply_collection": mock_reply_collection,
        }


@pytest.fixture
def mock_embedding():
    """Mock embedding function"""
    with patch("scripts.rag_retriever.RAGRetriever._create_embedding_fn") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def retriever(wiki_dir, data_dir, wiki_hash_path, mock_chromadb, mock_embedding):
    """创建测试用的 RAGRetriever 实例"""
    from scripts.rag_retriever import RAGRetriever
    r = RAGRetriever(
        wiki_dir=str(wiki_dir),
        vector_store_dir=str(data_dir / "vector_store"),
        reply_index_dir=str(data_dir / "reply_index"),
        use_online_embedding=False,
        wiki_hash_path=str(wiki_hash_path),
    )
    # 手动设置 mock collections（因为 __init__ 中已经创建了）
    r.wiki_collection = mock_chromadb["wiki_collection"]
    r.reply_collection = mock_chromadb["reply_collection"]
    return r


# ─── Markdown 分块测试 ──────────────────────────────────────────

class TestChunkMarkdown:
    """测试 Markdown 分块逻辑"""

    def test_chunk_by_headers(self) -> None:
        """按标题分块"""
        from scripts.rag_retriever import RAGRetriever
        text = "# 标题一\n内容1\n# 标题二\n内容2"
        chunks = RAGRetriever._chunk_markdown(text, "test.md")
        assert len(chunks) == 2
        assert chunks[0]["title"] == "标题一"
        assert chunks[1]["title"] == "标题二"

    def test_chunk_preserves_source(self) -> None:
        """分块保留来源文件名"""
        from scripts.rag_retriever import RAGRetriever
        chunks = RAGRetriever._chunk_markdown("# Test\ncontent", "wiki/doc.md")
        assert chunks[0]["source"] == "wiki/doc.md"

    def test_chunk_empty_text(self) -> None:
        """空文本返回空列表"""
        from scripts.rag_retriever import RAGRetriever
        chunks = RAGRetriever._chunk_markdown("", "test.md")
        assert chunks == []

    def test_chunk_no_headers(self) -> None:
        """无标题时整段作为一个块"""
        from scripts.rag_retriever import RAGRetriever
        chunks = RAGRetriever._chunk_markdown("一段普通文本内容", "test.md")
        assert len(chunks) == 1
        assert chunks[0]["title"] == ""

    def test_chunk_nested_headers(self) -> None:
        """多级标题分块"""
        from scripts.rag_retriever import RAGRetriever
        text = "# 一级标题\n## 二级标题\n内容\n### 三级标题\n更多内容"
        chunks = RAGRetriever._chunk_markdown(text, "test.md")
        assert len(chunks) >= 2


# ─── sync_wiki 测试 ──────────────────────────────────────────────

class TestSyncWiki:
    """测试 Wiki 增量同步"""

    def test_sync_new_file(self, retriever, wiki_dir, mock_chromadb) -> None:
        """新文件应被索引"""
        (wiki_dir / "test.md").write_text("# 测试\n这是新文件", encoding="utf-8")

        updated = retriever.sync_wiki()
        assert updated == 1
        mock_chromadb["wiki_collection"].add.assert_called_once()

    def test_sync_unchanged_file_skipped(self, retriever, wiki_dir, wiki_hash_path, mock_chromadb) -> None:
        """未变更文件应被跳过"""
        content = "# 测试\n这是已存在的文件"
        (wiki_dir / "existing.md").write_text(content, encoding="utf-8")

        # 预先写入相同的哈希
        import hashlib
        file_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
        with open(wiki_hash_path, "w") as f:
            json.dump({"existing.md": file_hash}, f)

        updated = retriever.sync_wiki()
        assert updated == 0
        mock_chromadb["wiki_collection"].add.assert_not_called()

    def test_sync_changed_file_updated(self, retriever, wiki_dir, wiki_hash_path, mock_chromadb) -> None:
        """变更文件应被重新索引"""
        (wiki_dir / "changed.md").write_text("# 新内容\n更新后的文件", encoding="utf-8")

        # 预先写入旧哈希
        with open(wiki_hash_path, "w") as f:
            json.dump({"changed.md": "old_hash_value"}, f)

        updated = retriever.sync_wiki()
        assert updated == 1
        mock_chromadb["wiki_collection"].delete.assert_called()
        mock_chromadb["wiki_collection"].add.assert_called()

    def test_sync_force_rebuilds_all(self, retriever, wiki_dir, wiki_hash_path, mock_chromadb) -> None:
        """force=True 时应全量重建"""
        content = "# 测试\n内容"
        (wiki_dir / "file.md").write_text(content, encoding="utf-8")

        # 即使哈希相同也应更新
        import hashlib
        file_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
        with open(wiki_hash_path, "w") as f:
            json.dump({"file.md": file_hash}, f)

        updated = retriever.sync_wiki(force=True)
        assert updated == 1

    def test_sync_multiple_files(self, retriever, wiki_dir, mock_chromadb) -> None:
        """多个文件应逐个处理"""
        (wiki_dir / "file1.md").write_text("# 文件1\n内容1", encoding="utf-8")
        (wiki_dir / "file2.md").write_text("# 文件2\n内容2", encoding="utf-8")

        updated = retriever.sync_wiki()
        assert updated == 2


# ─── retrieve 测试 ──────────────────────────────────────────────

class TestRetrieve:
    """测试 RAG 检索"""

    def test_retrieve_returns_results(self, retriever, mock_chromadb) -> None:
        """正常检索应返回结果"""
        mock_chromadb["reply_collection"].query.return_value = {
            "documents": [["真人回复内容"]],
            "distances": [[0.1]],  # 高相似度（低距离）
        }
        mock_chromadb["wiki_collection"].query.return_value = {
            "documents": [["Wiki 文档内容"]],
            "distances": [[0.2]],
        }

        results = retriever.retrieve("如何处理客户投诉？")
        assert len(results) >= 1

    def test_retrieve_reply_priority(self, retriever, mock_chromadb) -> None:
        """reply_index 结果应排在前面"""
        mock_chromadb["reply_collection"].query.return_value = {
            "documents": [["优先的真人回复"]],
            "distances": [[0.1]],
        }
        mock_chromadb["wiki_collection"].query.return_value = {
            "documents": [["Wiki 补充内容"]],
            "distances": [[0.2]],
        }

        results = retriever.retrieve("测试问题", k=3)
        assert results[0] == "优先的真人回复"

    def test_retrieve_threshold_filter(self, retriever, mock_chromadb) -> None:
        """低于阈值的结果应被过滤"""
        # 距离很大 → 相似度低
        mock_chromadb["reply_collection"].query.return_value = {
            "documents": [["不相关内容"]],
            "distances": [[100.0]],  # 距离极大，相似度极低
        }
        mock_chromadb["wiki_collection"].query.return_value = {
            "documents": [["也不相关"]],
            "distances": [[100.0]],
        }

        results = retriever.retrieve("查询", threshold=0.72)
        assert len(results) == 0

    def test_retrieve_empty_index(self, retriever, mock_chromadb) -> None:
        """空索引应返回空列表"""
        mock_chromadb["reply_collection"].query.side_effect = Exception("empty collection")
        mock_chromadb["wiki_collection"].query.side_effect = Exception("empty collection")

        results = retriever.retrieve("查询")
        assert results == []


# ─── index_human_reply 测试 ──────────────────────────────────────

class TestIndexHumanReply:
    """测试真人回复索引"""

    def test_index_with_high_weight(self, retriever, mock_chromadb) -> None:
        """索引真人回复应设置 weight=high 元数据"""
        retriever.index_human_reply(
            question="如何处理退款？",
            reply="需要先核实合同条款...",
            article_id="98765",
            thread_id="12345",
        )

        mock_chromadb["reply_collection"].add.assert_called_once()
        call_args = mock_chromadb["reply_collection"].add.call_args
        metadatas = call_args[1]["metadatas"]
        assert metadatas[0]["weight"] == "high"
        assert metadatas[0]["source"] == "human_reply"

    def test_index_document_format(self, retriever, mock_chromadb) -> None:
        """索引文档应包含 [问题] 和 [作者回复] 标记"""
        retriever.index_human_reply(
            question="客户投诉",
            reply="处理流程是...",
            article_id="111",
            thread_id="222",
        )

        call_args = mock_chromadb["reply_collection"].add.call_args
        documents = call_args[1]["documents"]
        assert "[问题]" in documents[0]
        assert "[作者回复]" in documents[0]

    def test_index_metadata_fields(self, retriever, mock_chromadb) -> None:
        """索引元数据应包含 article_id 和 thread_id"""
        retriever.index_human_reply(
            question="问题",
            reply="回复",
            article_id="AAA",
            thread_id="BBB",
        )

        call_args = mock_chromadb["reply_collection"].add.call_args
        metadatas = call_args[1]["metadatas"]
        assert metadatas[0]["article_id"] == "AAA"
        assert metadatas[0]["thread_id"] == "BBB"

    def test_index_id_format(self, retriever, mock_chromadb) -> None:
        """索引 ID 应为 human_{article_id}_{thread_id}"""
        retriever.index_human_reply(
            question="q", reply="r", article_id="A1", thread_id="T1"
        )

        call_args = mock_chromadb["reply_collection"].add.call_args
        ids = call_args[1]["ids"]
        assert ids[0] == "human_A1_T1"


# ─── embedding 模式测试 ──────────────────────────────────────────

class TestEmbeddingMode:
    """测试 embedding 模式切换"""

    def test_local_mode_default(self, wiki_dir, data_dir, mock_chromadb) -> None:
        """默认使用本地 embedding"""
        with patch("scripts.rag_retriever.RAGRetriever._create_local_embedding_fn") as mock_local, \
             patch("scripts.rag_retriever.RAGRetriever._create_online_embedding_fn") as mock_online:
            mock_local.return_value = MagicMock()
            mock_online.return_value = MagicMock()
            from scripts.rag_retriever import RAGRetriever
            r = RAGRetriever(
                wiki_dir=str(wiki_dir),
                vector_store_dir=str(data_dir / "vector_store"),
                reply_index_dir=str(data_dir / "reply_index"),
                use_online_embedding=False,
            )
            mock_local.assert_called_once()
            mock_online.assert_not_called()

    def test_online_mode_switch(self, wiki_dir, data_dir, mock_chromadb) -> None:
        """use_online_embedding=True 时使用线上 embedding"""
        with patch("scripts.rag_retriever.RAGRetriever._create_online_embedding_fn") as mock_online, \
             patch("scripts.rag_retriever.RAGRetriever._create_local_embedding_fn") as mock_local:
            mock_online.return_value = MagicMock()
            mock_local.return_value = MagicMock()
            from scripts.rag_retriever import RAGRetriever
            r = RAGRetriever(
                wiki_dir=str(wiki_dir),
                vector_store_dir=str(data_dir / "vector_store"),
                reply_index_dir=str(data_dir / "reply_index"),
                use_online_embedding=True,
            )
            mock_online.assert_called_once()
            mock_local.assert_not_called()
