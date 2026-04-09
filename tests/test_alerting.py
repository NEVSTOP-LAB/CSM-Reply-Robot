"""
AI-010: Alerting 单元测试
参考: docs/plan/README.md § AI-010

测试覆盖：
- 正常 Issue 创建
- 防重复（已有同标题 Issue 时跳过）
- Token 缺失时不创建
"""

from unittest.mock import patch, MagicMock
import pytest

from scripts.alerting import create_alert_issue, ALERT_LABEL


@pytest.fixture
def mock_env():
    """Mock 环境变量"""
    with patch.dict("os.environ", {
        "GITHUB_TOKEN": "test-token",
        "GITHUB_REPOSITORY": "owner/repo",
    }):
        yield


class TestCreateAlertIssue:
    """测试 GitHub Issue 告警创建"""

    @patch("scripts.alerting.requests.post")
    @patch("scripts.alerting._has_existing_issue", return_value=False)
    def test_create_issue_success(self, mock_exists, mock_post, mock_env) -> None:
        """正常创建 Issue"""
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {"html_url": "https://github.com/owner/repo/issues/1"},
        )

        result = create_alert_issue("auth_failure", "Cookie 已失效")
        assert result is True
        mock_post.assert_called_once()

        # 检查 payload
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert "[Bot Alert]" in payload["title"]
        assert "auth_failure" in payload["title"]
        assert ALERT_LABEL in payload["labels"]

    @patch("scripts.alerting._has_existing_issue", return_value=True)
    def test_skip_duplicate_issue(self, mock_exists, mock_env) -> None:
        """已有同标题 Issue 时跳过"""
        result = create_alert_issue("rate_limit", "429 Too Many Requests")
        assert result is True

    def test_missing_token_returns_false(self) -> None:
        """缺少 GITHUB_TOKEN 时返回 False"""
        with patch.dict("os.environ", {}, clear=True):
            result = create_alert_issue("test", "test message")
            assert result is False

    @patch("scripts.alerting.requests.post")
    @patch("scripts.alerting._has_existing_issue", return_value=False)
    def test_api_failure_returns_false(self, mock_exists, mock_post, mock_env) -> None:
        """API 调用失败时返回 False"""
        mock_post.return_value = MagicMock(
            status_code=403,
            text="Forbidden",
        )
        result = create_alert_issue("test", "test")
        assert result is False


class TestHasExistingIssue:
    """测试重复检测"""

    @patch("scripts.alerting.requests.get")
    def test_finds_existing_issue(self, mock_get) -> None:
        """发现同标题 open Issue"""
        from scripts.alerting import _has_existing_issue

        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"title": "[Bot Alert] auth_failure: Cookie 失效"}],
        )

        result = _has_existing_issue(
            "owner/repo",
            "[Bot Alert] auth_failure: Cookie 失效",
            {"Authorization": "token xxx"},
        )
        assert result is True

    @patch("scripts.alerting.requests.get")
    def test_no_existing_issue(self, mock_get) -> None:
        """无同标题 Issue"""
        from scripts.alerting import _has_existing_issue

        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [],
        )

        result = _has_existing_issue(
            "owner/repo", "新标题", {"Authorization": "token xxx"},
        )
        assert result is False
