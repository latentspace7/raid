import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import Settings, load_settings
from src.raid import get_openai_client


def test_missing_configuration_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "do-not-log-this-password")
    with pytest.raises(ValueError) as exc:
        load_settings()
    assert "client_id" in str(exc.value)
    assert "do-not-log-this-password" not in str(exc.value)


def test_legacy_openai_key_remains_supported(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = settings.model_dump(exclude={"openai_api_key"})
    monkeypatch.setenv("OPEN_AI_TOKEN", "legacy-test-key")
    configured = Settings(**values)
    assert configured.openai_api_key.get_secret_value() == "legacy-test-key"


def test_hosted_openai_requires_key(settings: Settings) -> None:
    values = settings.model_dump()
    values["openai_api_key"] = None
    with pytest.raises(ValidationError, match="OPENAI_API_KEY is required"):
        Settings(**values)


@pytest.mark.parametrize("entrypoint", [["-m", "src.raid"], ["src/raid.py"]])
def test_cli_fails_before_network_when_unconfigured(entrypoint: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, *entrypoint],
        cwd=Path(__file__).resolve().parents[1],
        env={"PYTHON_DOTENV_DISABLED": "1"},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "Invalid configuration" in result.stderr
    assert "Traceback" not in result.stderr


async def test_local_endpoint_can_run_without_api_key(settings: Settings) -> None:
    values = settings.model_dump()
    values.update(openai_api_key=None, openai_base_url="http://localhost:8080")
    configured = Settings(**values)
    async with get_openai_client(configured) as client:
        assert str(client.base_url) == "http://localhost:8080/"
        assert client.max_retries == 0
    assert client.is_closed()


@pytest.mark.parametrize(
    "recipient", ["", "missing-at-sign", "victim@example.com\r\nBcc: other@example.com"]
)
def test_invalid_email_configuration_is_rejected(
    settings: Settings, recipient: str
) -> None:
    values = settings.model_dump()
    values["to_email"] = recipient
    with pytest.raises(ValidationError):
        Settings(**values)
