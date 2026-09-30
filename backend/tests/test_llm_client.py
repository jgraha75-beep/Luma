from luma.config import Settings, settings
from luma.services.llm_client import (
    _normalize_reasoning_response,
    build_litellm_target,
    get_model_route_status,
    get_role_route_status,
)


def test_blank_primary_model_uses_supported_default():
    config = Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        jwt_secret="x" * 32,
        meal_planner_model="",
    )

    assert config.meal_planner_model == "anthropic/claude-sonnet-4-5"


def test_gemini_route_reports_missing_credentials(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")

    status = get_model_route_status("gemini/gemini-3.5-flash")

    assert status["ready"] is False
    assert status["provider"] == "gemini"
    assert status["issue"] == "Gemini API key is missing."


def test_anthropic_route_requires_workspace_id(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "anthropic_workspace_id", "")

    status = get_model_route_status("anthropic/claude-sonnet-4-5")

    assert status["ready"] is False
    assert status["issue"] == "Anthropic workspace ID is missing."


def test_anthropic_target_sends_workspace_header(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_workspace_id", " wrkspc_test ")

    target = build_litellm_target("anthropic/claude-sonnet-4-5")

    assert target == {
        "model": "anthropic/claude-sonnet-4-5",
        "extra_headers": {"anthropic-workspace-id": "wrkspc_test"},
    }


def test_anthropic_target_omits_blank_workspace_header(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_workspace_id", "")

    target = build_litellm_target("anthropic/claude-sonnet-4-5")

    assert target == {"model": "anthropic/claude-sonnet-4-5"}


def test_role_uses_ready_fallback_when_primary_is_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    status = get_role_route_status(
        "anthropic/claude-sonnet-4-5",
        "gemini/gemini-3.5-flash",
    )

    assert status["ready"] is True
    assert status["active"] == "gemini/gemini-3.5-flash"
    assert status["using_fallback"] is True


def test_normalize_reasoning_response_dict():
    # Test dictionary input
    response = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "reasoning": "This is reasoning output"
                }
            }
        ]
    }
    _normalize_reasoning_response(response)
    assert response["choices"][0]["message"]["content"] == "This is reasoning output"


def test_normalize_reasoning_response_dict_reasoning_content():
    # Test dictionary input with reasoning_content
    response = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "reasoning_content": "This is reasoning content"
                }
            }
        ]
    }
    _normalize_reasoning_response(response)
    assert response["choices"][0]["message"]["content"] == "This is reasoning content"


def test_normalize_reasoning_response_object():
    # Test object input
    class Message:
        def __init__(self, content, reasoning):
            self.content = content
            self.reasoning = reasoning

    class Choice:
        def __init__(self, message):
            self.message = message

    class ModelResponse:
        def __init__(self, choices):
            self.choices = choices

    msg = Message("", "Object reasoning output")
    choice = Choice(msg)
    response = ModelResponse([choice])

    _normalize_reasoning_response(response)
    assert response.choices[0].message.content == "Object reasoning output"


def test_normalize_reasoning_response_object_dict_hybrid():
    # Test where object contains content as both attribute and dict key
    class Message(dict):
        def __init__(self, content, reasoning):
            super().__init__()
            self["content"] = content
            self["reasoning"] = reasoning
            self.content = content
            self.reasoning = reasoning

    class Choice:
        def __init__(self, message):
            self.message = message

    class ModelResponse:
        def __init__(self, choices):
            self.choices = choices

    msg = Message("", "Hybrid reasoning output")
    choice = Choice(msg)
    response = ModelResponse([choice])

    _normalize_reasoning_response(response)
    assert response.choices[0].message.content == "Hybrid reasoning output"
    assert response.choices[0].message["content"] == "Hybrid reasoning output"


def test_normalize_reasoning_response_no_override_if_content_exists():
    response = {
        "choices": [
            {
                "message": {
                    "content": "Existing content",
                    "reasoning": "Reasoning content"
                }
            }
        ]
    }
    _normalize_reasoning_response(response)
    assert response["choices"][0]["message"]["content"] == "Existing content"
