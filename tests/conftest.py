import os
import socket
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from src.config import Settings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    names = {name.upper() for name in Settings.model_fields} | {"OPEN_AI_TOKEN"}
    for name in os.environ:
        if name.upper() in names:
            monkeypatch.delenv(name)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    with patch.object(
        socket.socket,
        "connect",
        side_effect=AssertionError("Network disabled in tests"),
    ):
        yield


@pytest.fixture
def settings() -> Settings:
    return Settings(
        client_id="test-client",
        client_secret="test-secret",
        gmail_email="sender@example.com",
        gmail_app_password="test-password",
        to_email="reader@example.com",
        openai_api_key="test-openai-key",
        digest_api_token="test-digest-token",
    )
