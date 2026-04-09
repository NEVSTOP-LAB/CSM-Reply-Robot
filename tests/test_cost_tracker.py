"""
AI-010 + AI-012: Alerting + CostTracker 测试
"""

from pathlib import Path
from datetime import datetime, timezone

import pytest

from scripts.cost_tracker import CostTracker


# ─── fixtures ──────────────────────────────────────────────────

@pytest.fixture
def tracker(tmp_path: Path) -> CostTracker:
    """创建测试用 CostTracker"""
    return CostTracker(log_path=str(tmp_path / "cost_log.json"))


# ─── CostTracker 测试 ──────────────────────────────────────────

class TestCostTracker:
    """测试费用追踪器"""

    def test_record_call(self, tracker) -> None:
        """记录调用后应保存到内部列表"""
        tracker.record_call(
            model="deepseek-chat",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.001,
        )
        assert len(tracker._calls) == 1
        assert tracker._calls[0]["model"] == "deepseek-chat"

    def test_daily_summary(self, tracker) -> None:
        """每日汇总应正确统计"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        tracker.record_call("model", 100, 50, cost_usd=0.001)
        tracker.record_call("model", 200, 100, cost_usd=0.002)

        summary = tracker.get_daily_summary(today)
        assert summary["call_count"] == 2
        assert summary["total_prompt_tokens"] == 300
        assert summary["total_completion_tokens"] == 150
        assert abs(summary["total_cost_usd"] - 0.003) < 0.000001

    def test_over_budget(self, tracker) -> None:
        """超预算检测"""
        tracker.record_call("model", 100, 50, cost_usd=0.50)
        assert tracker.is_over_budget(0.50) is True
        assert tracker.is_over_budget(1.00) is False

    def test_save_and_load(self, tracker, tmp_path) -> None:
        """持久化保存和加载"""
        tracker.record_call("model", 100, 50, cost_usd=0.001)
        tracker.save_to_file()

        # 创建新实例，从文件加载
        tracker2 = CostTracker(log_path=str(tmp_path / "cost_log.json"))
        assert len(tracker2._calls) == 1
        assert tracker2._calls[0]["cost_usd"] == 0.001

    def test_empty_summary(self, tracker) -> None:
        """无记录时汇总应为零"""
        summary = tracker.get_daily_summary("2099-01-01")
        assert summary["call_count"] == 0
        assert summary["total_cost_usd"] == 0.0

    def test_cache_hit_tracking(self, tracker) -> None:
        """缓存命中 token 应正确记录"""
        tracker.record_call(
            model="deepseek-chat",
            prompt_tokens=100,
            completion_tokens=50,
            cache_hit_tokens=80,
            cost_usd=0.001,
        )

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        summary = tracker.get_daily_summary(today)
        assert summary["total_cache_hit_tokens"] == 80
