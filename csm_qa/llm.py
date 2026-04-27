"""LLM 调用封装（OpenAI 兼容协议）。

仅承担：发送 messages → 拿到回复 + token 用量；含指数退避重试。
不再处理预算、风险评估、文章摘要等业务逻辑（这些已在重构中删除）。
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from openai import APIConnectionError, APIError, OpenAI, RateLimitError

from csm_qa.types import Usage

logger = logging.getLogger(__name__)


class LLMClient:
    """对 OpenAI 兼容 Chat Completion API 的极简封装。"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.5,
        max_retries: int = 3,
        timeout: float = 60.0,
    ) -> None:
        """初始化 LLM 客户端。

        Args:
            api_key: API Key。
            base_url: API base URL（含或不含 ``/v1`` 由具体厂商决定）。
            model: 模型名。
            max_tokens: 单次回复的 token 上限。
            temperature: 采样温度。
            max_retries: 限流/网络错误的最大重试次数。
            timeout: 单次请求超时秒数。
        """
        if not api_key:
            raise ValueError("api_key 不可为空")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max(1, max_retries)

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )
        logger.debug(
            "LLMClient 初始化: model=%s, base_url=%s", model, base_url
        )

    def chat(
        self,
        messages: list[dict],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> tuple[str, Usage]:
        """发送一组 messages，返回回复文本与 token 用量。

        Args:
            messages: OpenAI 兼容的 ``messages`` 列表。
            max_tokens: 覆盖默认 ``max_tokens``。
            temperature: 覆盖默认 ``temperature``。

        Returns:
            ``(reply_text, usage)``。

        Raises:
            Exception: 重试耗尽后抛出最后一次异常。
        """
        last_error: Optional[BaseException] = None
        for attempt in range(self.max_retries):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                    temperature=(
                        temperature if temperature is not None else self.temperature
                    ),
                )
                break
            except RateLimitError as exc:
                last_error = exc
                wait = 2 ** attempt
                logger.warning(
                    "LLM 限流（第 %d/%d 次），等待 %ds 后重试",
                    attempt + 1, self.max_retries, wait,
                )
                time.sleep(wait)
            except (APIConnectionError, APIError) as exc:
                last_error = exc
                # 仅在网络错误或 5xx 上重试，4xx 直接抛出
                status = getattr(exc, "status_code", None)
                if isinstance(exc, APIConnectionError) or (status and status >= 500):
                    wait = 2 ** attempt
                    logger.warning(
                        "LLM 服务端错误（第 %d/%d 次）: %s",
                        attempt + 1, self.max_retries, exc,
                    )
                    time.sleep(wait)
                    continue
                raise
        else:
            # 重试耗尽
            assert last_error is not None
            raise last_error

        text = response.choices[0].message.content or ""
        usage_obj = response.usage
        usage = Usage(
            prompt_tokens=getattr(usage_obj, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage_obj, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage_obj, "total_tokens", 0) or 0,
        )
        return text, usage
