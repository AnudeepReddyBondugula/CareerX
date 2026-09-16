import pytest

from careerx.ai.providers.base import (
    ProviderError,
    ProviderNotConfigured,
    ProviderRequestError,
    retry_with_backoff,
)
from careerx.ai.providers.factory import build_provider
from careerx.ai.providers.schema import to_strict_json_schema
from careerx.config.settings import Settings
from careerx.models import JobDescription, Resume

# ----------------------------------------------------------------------
# Retry
# ----------------------------------------------------------------------


def test_a_successful_call_is_not_retried() -> None:
    calls = []

    def operation() -> str:
        calls.append(1)
        return "ok"

    assert retry_with_backoff(operation, attempts=3, sleep=lambda _: None) == "ok"
    assert len(calls) == 1


def test_a_transient_failure_is_retried_then_succeeds() -> None:
    calls: list[int] = []

    def operation() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("flaky")
        return "ok"

    assert retry_with_backoff(operation, attempts=3, sleep=lambda _: None) == "ok"
    assert len(calls) == 3


def test_exhausted_retries_raise_a_provider_error_naming_the_cause() -> None:
    def operation() -> str:
        raise TimeoutError("still down")

    with pytest.raises(ProviderError, match="still down"):
        retry_with_backoff(operation, attempts=2, sleep=lambda _: None)


def test_backoff_delays_grow() -> None:
    delays: list[float] = []

    def operation() -> str:
        raise ValueError("no")

    with pytest.raises(ProviderError):
        retry_with_backoff(operation, attempts=4, base_delay=1.0, sleep=delays.append)

    assert len(delays) == 3
    assert delays[0] < delays[-1]


def test_a_configuration_error_is_not_retried() -> None:
    calls: list[int] = []

    def operation() -> str:
        calls.append(1)
        raise ProviderNotConfigured("no key")

    with pytest.raises(ProviderNotConfigured):
        retry_with_backoff(operation, attempts=5, sleep=lambda _: None)

    assert len(calls) == 1


# ----------------------------------------------------------------------
# Strict schema conversion
# ----------------------------------------------------------------------


def _walk(node: object) -> list[dict]:
    objects: list[dict] = []

    if isinstance(node, dict):
        if node.get("type") == "object":
            objects.append(node)
        for value in node.values():
            objects.extend(_walk(value))
    elif isinstance(node, list):
        for item in node:
            objects.extend(_walk(item))

    return objects


@pytest.mark.parametrize("model", [Resume, JobDescription])
def test_every_object_is_closed_and_fully_required(model: type) -> None:
    schema = to_strict_json_schema(model)

    for obj in _walk(schema):
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])


def test_unsupported_keywords_are_stripped() -> None:
    import json

    serialised = json.dumps(to_strict_json_schema(Resume))

    assert '"default"' not in serialised
    assert '"format"' not in serialised


def test_nested_definitions_are_preserved() -> None:
    schema = to_strict_json_schema(Resume)

    assert "$defs" in schema
    assert "Experience" in schema["$defs"]


# ----------------------------------------------------------------------
# Factory
# ----------------------------------------------------------------------


def test_the_factory_refuses_gemini_without_a_key() -> None:
    settings = Settings(_env_file=None, llm_provider="gemini", google_api_key=None)

    with pytest.raises(ProviderNotConfigured, match="GOOGLE_API_KEY"):
        build_provider(settings)


def test_the_factory_refuses_openai_without_a_key() -> None:
    settings = Settings(_env_file=None, llm_provider="openai", openai_api_key=None)

    with pytest.raises(ProviderNotConfigured, match="OPENAI_API_KEY"):
        build_provider(settings)


@pytest.mark.parametrize(
    ("provider_name", "key_field", "expected_model_field"),
    [("gemini", "google_api_key", "gemini_model"), ("openai", "openai_api_key", "openai_model")],
)
def test_the_factory_builds_the_selected_provider(
    provider_name: str,
    key_field: str,
    expected_model_field: str,
) -> None:
    settings = Settings(_env_file=None, llm_provider=provider_name, **{key_field: "test-key"})

    provider = build_provider(settings)

    assert provider.name == provider_name
    assert provider.chat_model == getattr(settings, expected_model_field)


def test_the_active_key_follows_the_selected_provider() -> None:
    settings = Settings(_env_file=None, llm_provider="openai", google_api_key="g", openai_api_key="o")

    assert settings.active_api_key == "o"
    assert settings.llm_configured


# ----------------------------------------------------------------------
# Retryability classification
# ----------------------------------------------------------------------


def test_a_non_retryable_error_fails_on_the_first_attempt() -> None:
    calls: list[int] = []

    def operation() -> str:
        calls.append(1)
        raise ValueError("bad api key")

    with pytest.raises(ProviderRequestError, match="bad api key"):
        retry_with_backoff(operation, attempts=5, sleep=lambda _: None, retryable=lambda _: False)

    assert len(calls) == 1


def test_gemini_does_not_retry_an_invalid_key() -> None:
    from google.genai import errors

    from careerx.ai.providers.gemini import _is_retryable

    invalid_key = errors.ClientError(400, {"error": {"message": "API key not valid"}})

    assert not _is_retryable(invalid_key)


def test_gemini_retries_a_rate_limit() -> None:
    from google.genai import errors

    from careerx.ai.providers.gemini import _is_retryable

    assert _is_retryable(errors.ClientError(429, {"error": {"message": "quota"}}))
    assert _is_retryable(TimeoutError("connection reset"))


def test_openai_retries_server_errors_but_not_auth_errors() -> None:
    import httpx
    from openai import APIStatusError

    from careerx.ai.providers.openai_provider import _is_retryable

    def status_error(code: int) -> APIStatusError:
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        return APIStatusError("boom", response=httpx.Response(code, request=request), body=None)

    assert not _is_retryable(status_error(401))
    assert not _is_retryable(status_error(400))
    assert _is_retryable(status_error(429))
    assert _is_retryable(status_error(503))
