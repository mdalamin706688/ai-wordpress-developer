"""Free models without a provider key should remap to GLM/NIM that have keys."""

from ai_agent.api.lab import remap_models_missing_keys


def test_gemini_without_key_remaps_to_glm():
    selected, swaps = remap_models_missing_keys(
        ["gemini-3.5-flash-lite"],
        {
            "gemini_api_key": "",
            "zai_api_key": "zai-test-key",
            "nvidia_api_key": "nv-test-key",
        },
    )
    assert selected == ["glm-4.5-flash"]
    assert swaps == [{"from": "gemini-3.5-flash-lite", "to": "glm-4.5-flash"}]


def test_gemini_kept_when_key_present():
    selected, swaps = remap_models_missing_keys(
        ["gemini-3.5-flash-lite"],
        {"gemini_api_key": "AIzaSy-test-key-long-enough"},
    )
    assert selected == ["gemini-3.5-flash-lite"]
    assert swaps == []


def test_stack_preserves_ready_and_remaps_missing():
    selected, swaps = remap_models_missing_keys(
        ["glm-4.5-flash", "gemini-3.5-flash-lite"],
        {
            "gemini_api_key": "",
            "zai_api_key": "zai-test-key",
            "nvidia_api_key": "",
        },
    )
    assert selected == ["glm-4.5-flash"]
    assert swaps == [{"from": "gemini-3.5-flash-lite", "to": "glm-4.5-flash"}]
