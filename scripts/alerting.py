"""
AI-010: GitHub Issue 自动告警
参考: docs/plan/README.md § AI-010

功能：
1. create_alert_issue(): 调用 GitHub API 创建告警 Issue
2. 告警场景：Cookie 失效 (auth_failure)、限流 (rate_limit)、连续失败 (consecutive_fail)、预算超限 (budget_exceeded)
3. 防重复：检查已有同 title 的 open issue，避免重复创建

设计说明：
- 使用 GITHUB_TOKEN 调用 GitHub REST API
- Issue 标签统一为 "bot-alert"
- 连续失败计数由主流程维护，告警模块只负责创建 Issue
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# 告警 Issue 标签
ALERT_LABEL = "bot-alert"


def create_alert_issue(
    alert_type: str,
    message: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> bool:
    """
    创建 GitHub Issue 告警
    参考: docs/plan/README.md § AI-010

    防重复：先检查是否存在同 title 的 open issue。

    Args:
        alert_type: 告警类型 (auth_failure / rate_limit / consecutive_fail / budget_exceeded)
        message: 告警详细信息
        repo: 仓库（owner/repo 格式），默认从 GITHUB_REPOSITORY 读取
        token: GitHub Token，默认从 GITHUB_TOKEN 读取

    Returns:
        True 表示成功创建或已存在，False 表示创建失败
    """
    token = token or os.environ.get("GITHUB_TOKEN", "")
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "")

    if not token or not repo:
        logger.warning("缺少 GITHUB_TOKEN 或 GITHUB_REPOSITORY，无法创建告警 Issue")
        return False

    # 告警标题
    title = f"[Bot Alert] {alert_type}: {message[:80]}"

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # 防重复：检查已有同标题的 open issue
    # 参考: docs/plan/README.md § AI-010 第 3 点
    if _has_existing_issue(repo, title, headers):
        logger.info("已存在同标题的 open Issue，跳过创建: %s", title)
        return True

    # 创建 Issue
    url = f"https://api.github.com/repos/{repo}/issues"
    body = (
        f"## 🚨 Bot 告警\n\n"
        f"**类型**: `{alert_type}`\n\n"
        f"**详情**:\n{message}\n\n"
        f"---\n"
        f"*此 Issue 由 Zhihu CSM Reply Bot 自动创建*"
    )
    payload = {
        "title": title,
        "body": body,
        "labels": [ALERT_LABEL],
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 201:
            issue_url = response.json().get("html_url", "")
            logger.info("告警 Issue 创建成功: %s", issue_url)
            return True
        else:
            logger.error(
                "告警 Issue 创建失败 (HTTP %d): %s",
                response.status_code, response.text[:200],
            )
            return False
    except Exception as e:
        logger.error("告警 Issue 创建异常: %s", e)
        return False


def _has_existing_issue(repo: str, title: str, headers: dict) -> bool:
    """
    检查是否存在同标题的 open issue
    参考: docs/plan/README.md § AI-010 第 3 点 — 防重复

    Args:
        repo: 仓库（owner/repo 格式）
        title: Issue 标题
        headers: GitHub API 请求头

    Returns:
        True 如果已存在
    """
    url = f"https://api.github.com/repos/{repo}/issues"
    params = {
        "state": "open",
        "labels": ALERT_LABEL,
        "per_page": 30,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            issues = response.json()
            for issue in issues:
                if issue.get("title") == title:
                    return True
        return False
    except Exception as e:
        logger.warning("检查已有 Issue 失败: %s", e)
        return False
