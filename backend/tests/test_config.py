"""Settings: env parsing and secret handling."""

from pydantic import SecretStr

from core.config import Settings


def make(**env: str) -> Settings:
    # _env_file=None: ignore the real .env so the test only sees what it passes in.
    return Settings(_env_file=None, database_url="postgresql+asyncpg://x@y/z", **env)  # type: ignore[arg-type]


def test_empty_api_key_means_missing():
    # docker-compose passes unset optional keys as "" via ${VAR:-}
    assert make(anthropic_api_key="").anthropic_api_key is None


def test_secrets_are_masked_when_printed():
    settings = make(anthropic_api_key="sk-ant-very-secret")
    assert isinstance(settings.anthropic_api_key, SecretStr)
    assert "very-secret" not in repr(settings)
    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-very-secret"


def test_repo_files_resolve():
    settings = make()
    assert settings.models_file.name == "models.yaml" and settings.models_file.exists()
    assert (settings.prompts_dir / "chat_system.yaml").exists()
