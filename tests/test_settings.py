import pytest
from pydantic import ValidationError

from careerx.config.settings import Settings


def test_cors_origins_accept_a_comma_separated_string() -> None:
    settings = Settings(_env_file=None, cors_allow_origins="https://a.com, https://b.com")

    assert settings.cors_allow_origins == ["https://a.com", "https://b.com"]


def test_cors_origins_accept_a_json_list() -> None:
    assert Settings(_env_file=None, cors_allow_origins='["https://a.com"]').cors_allow_origins == ["https://a.com"]


def test_an_empty_cors_string_means_no_origins() -> None:
    assert Settings(_env_file=None, cors_allow_origins="  ").cors_allow_origins == []


def test_log_level_is_normalised() -> None:
    assert Settings(_env_file=None, log_level="debug").log_level == "DEBUG"


def test_llm_configured_is_false_without_a_key() -> None:
    assert not Settings(_env_file=None, llm_provider="gemini").llm_configured


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_retries", 0),
        ("retrieval_top_k", 0),
        ("port", 70000),
        ("artifact_ttl_seconds", 5),
        ("temperature", "hot"),
        ("llm_provider", "anthropic-but-not-configured-here"),
    ],
)
def test_out_of_range_configuration_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_environment_variables_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "openai"
    assert settings.openai_model == "gpt-4.1-mini"
