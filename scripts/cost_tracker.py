"""
AI-012: Token 计数与费用追踪
参考: docs/plan/README.md § AI-012, docs/调研/06-Token优化策略.md

功能：
1. CostTracker: 记录每次 LLM 调用的 token 使用量和费用
2. record_call(): 记录单次调用
3. get_daily_summary(): 生成每日费用汇总
4. save_to_file() / load_from_file(): 持久化到 data/cost_log.json
5. is_over_budget(): 判断是否超预算

设计说明：
- 费用数据以 JSON 格式持久化，按日期分组
- 支持 DeepSeek 缓存命中折扣
- 与 LLMClient._track_cost 配合使用
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CostTracker:
    """
    Token 费用追踪器
    参考: docs/plan/README.md § AI-012
    """

    def __init__(self, log_path: Optional[str] = None) -> None:
        """
        初始化费用追踪器

        Args:
            log_path: 费用日志文件路径（默认 data/cost_log.json）
        """
        self.log_path = Path(log_path) if log_path else None
        self._calls: list[dict] = []
        self._daily_totals: dict[str, float] = defaultdict(float)

        # 从文件加载历史数据
        if self.log_path and self.log_path.exists():
            self.load_from_file()

    def record_call(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cache_hit_tokens: int = 0,
        cost_usd: float = 0.0,
        article_id: str = "",
        comment_id: str = "",
    ) -> None:
        """
        记录一次 LLM 调用
        参考: docs/plan/README.md § AI-012 第 1 点

        Args:
            model: 模型名称
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
            cache_hit_tokens: 缓存命中 token 数
            cost_usd: 本次费用（USD）
            article_id: 文章 ID
            comment_id: 评论 ID
        """
        now = datetime.now(timezone.utc)
        date_key = now.strftime("%Y-%m-%d")

        record = {
            "timestamp": now.isoformat(),
            "date": date_key,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cache_hit_tokens": cache_hit_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost_usd": round(cost_usd, 6),
            "article_id": article_id,
            "comment_id": comment_id,
        }

        self._calls.append(record)
        self._daily_totals[date_key] += cost_usd

        logger.debug(
            "费用记录: model=%s, tokens=%d, cost=$%.6f",
            model, prompt_tokens + completion_tokens, cost_usd,
        )

    def get_daily_summary(self, date: Optional[str] = None) -> dict:
        """
        获取每日费用汇总
        参考: docs/plan/README.md § AI-012 第 2 点

        Args:
            date: 日期（YYYY-MM-DD 格式），默认今天

        Returns:
            汇总字典
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        day_calls = [c for c in self._calls if c["date"] == date]

        total_cost = sum(c["cost_usd"] for c in day_calls)
        total_prompt = sum(c["prompt_tokens"] for c in day_calls)
        total_completion = sum(c["completion_tokens"] for c in day_calls)
        total_cache_hit = sum(c["cache_hit_tokens"] for c in day_calls)

        return {
            "date": date,
            "call_count": len(day_calls),
            "total_cost_usd": round(total_cost, 6),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_cache_hit_tokens": total_cache_hit,
            "total_tokens": total_prompt + total_completion,
        }

    def is_over_budget(self, budget_usd: float, date: Optional[str] = None) -> bool:
        """
        判断是否超预算
        参考: docs/plan/README.md § AI-012 第 3 点

        Args:
            budget_usd: 预算上限（USD）
            date: 日期

        Returns:
            True 如果超预算
        """
        summary = self.get_daily_summary(date)
        return summary["total_cost_usd"] >= budget_usd

    def save_to_file(self) -> None:
        """持久化费用记录到文件"""
        if not self.log_path:
            return

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "calls": self._calls,
            "daily_totals": dict(self._daily_totals),
        }
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("费用记录已保存: %s", self.log_path)

    def load_from_file(self) -> None:
        """从文件加载费用记录"""
        if not self.log_path or not self.log_path.exists():
            return

        with open(self.log_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._calls = data.get("calls", [])
        self._daily_totals = defaultdict(float, data.get("daily_totals", {}))

        logger.info("费用记录已加载: %d 条", len(self._calls))
