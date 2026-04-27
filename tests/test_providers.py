"""Provider 预设测试。"""

import pytest

from csm_qa.providers import get_preset, list_providers, resolve_endpoint


def test_list_providers_only_two():
    assert set(list_providers()) == {"deepseek", "openai_compatible"}


def test_get_preset_deepseek():
    p = get_preset("deepseek")
    assert p.base_url == "https://api.deepseek.com"
    assert p.default_model == "deepseek-chat"


def test_get_preset_unknown_raises():
    with pytest.raises(ValueError):
        get_preset("openai")


def test_resolve_endpoint_deepseek_defaults():
    base, model = resolve_endpoint("deepseek", None, None)
    assert base == "https://api.deepseek.com"
    assert model == "deepseek-chat"


def test_resolve_endpoint_user_override():
    base, model = resolve_endpoint(
        "deepseek", "https://my-proxy/v1", "deepseek-coder"
    )
    assert base == "https://my-proxy/v1"
    assert model == "deepseek-coder"


def test_resolve_endpoint_openai_compatible_requires_both():
    with pytest.raises(ValueError):
        resolve_endpoint("openai_compatible", None, "any-model")
    with pytest.raises(ValueError):
        resolve_endpoint("openai_compatible", "https://x/v1", None)


def test_resolve_endpoint_openai_compatible_ok():
    base, model = resolve_endpoint(
        "openai_compatible", "https://api.moonshot.cn/v1", "moonshot-v1-8k"
    )
    assert base == "https://api.moonshot.cn/v1"
    assert model == "moonshot-v1-8k"


def test_provider_name_case_insensitive():
    p = get_preset("DeepSeek")
    assert p.name == "deepseek"
