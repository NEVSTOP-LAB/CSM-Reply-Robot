"""LLM 供应商预设。

仅支持两类：

- ``deepseek``：DeepSeek 官方端点（OpenAI 兼容协议）
- ``openai_compatible``：任意 OpenAI 兼容服务（OpenAI 官方、Moonshot、智谱 GLM、
  本地 vLLM/Ollama OpenAI 兼容端点等），由用户自行提供 ``base_url`` 与 ``model``
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderPreset:
    """LLM 供应商预设。"""

    name: str
    base_url: str
    default_model: str


_PRESETS: dict[str, ProviderPreset] = {
    "deepseek": ProviderPreset(
        name="deepseek",
        base_url="https://api.deepseek.com",
        default_model="deepseek-chat",
    ),
    "openai_compatible": ProviderPreset(
        name="openai_compatible",
        # 留空，必须由调用方显式提供 base_url
        base_url="",
        default_model="",
    ),
}


def list_providers() -> list[str]:
    """返回所有受支持的 provider 名。"""
    return list(_PRESETS.keys())


def get_preset(provider: str) -> ProviderPreset:
    """按名称获取 provider 预设。

    Args:
        provider: provider 名，参见 :func:`list_providers`。

    Raises:
        ValueError: provider 名未注册。
    """
    key = (provider or "").lower().strip()
    if key not in _PRESETS:
        raise ValueError(
            f"未知 provider: {provider!r}，可选: {list_providers()}"
        )
    return _PRESETS[key]


def resolve_endpoint(
    provider: str,
    base_url: str | None,
    model: str | None,
) -> tuple[str, str]:
    """根据 provider 与用户覆盖参数解析最终 ``(base_url, model)``。

    Args:
        provider: provider 名。
        base_url: 用户传入的 base_url，``None`` 时使用预设。
        model: 用户传入的 model，``None`` 时使用预设。

    Returns:
        ``(base_url, model)`` 元组。

    Raises:
        ValueError: 当 provider 为 ``openai_compatible`` 且未提供 base_url 或 model。
    """
    preset = get_preset(provider)
    final_base = base_url or preset.base_url
    final_model = model or preset.default_model

    if not final_base:
        raise ValueError(
            f"provider={provider!r} 必须显式提供 base_url"
        )
    if not final_model:
        raise ValueError(
            f"provider={provider!r} 必须显式提供 model"
        )
    return final_base, final_model
