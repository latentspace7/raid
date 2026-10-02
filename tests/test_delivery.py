import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiosmtplib
import pytest

from src.raid import send_email


def smtp_client() -> MagicMock:
    smtp = MagicMock()
    smtp.connect = AsyncMock()
    smtp.send_message = AsyncMock()
    smtp.quit = AsyncMock()
    return smtp


async def deliver() -> bool:
    return await send_email(
        "Digest",
        "<p>Summary</p>",
        "Summary",
        "to@example.com",
        "from@example.com",
        "password",
    )


async def test_falls_back_only_when_connection_fails() -> None:
    first, second = smtp_client(), smtp_client()
    first.connect.side_effect = aiosmtplib.SMTPConnectError("Unavailable")
    with patch("src.raid.aiosmtplib.SMTP", side_effect=[first, second]) as factory:
        assert await deliver()
    assert [call.kwargs["port"] for call in factory.call_args_list] == [465, 587]
    first.send_message.assert_not_awaited()
    second.send_message.assert_awaited_once()
    first.close.assert_called_once()
    second.close.assert_called_once()


async def test_does_not_retry_ambiguous_delivery() -> None:
    smtp = smtp_client()
    smtp.send_message.side_effect = aiosmtplib.SMTPTimeoutError("Response lost")
    with patch("src.raid.aiosmtplib.SMTP", return_value=smtp) as factory:
        assert not await deliver()
    factory.assert_called_once()
    smtp.close.assert_called_once()


async def test_quit_failure_does_not_resend_accepted_message() -> None:
    smtp = smtp_client()
    smtp.quit.side_effect = aiosmtplib.SMTPTimeoutError("QUIT failed")
    with patch("src.raid.aiosmtplib.SMTP", return_value=smtp) as factory:
        assert await deliver()
    factory.assert_called_once()
    smtp.send_message.assert_awaited_once()
    message = smtp.send_message.call_args.args[0]
    assert message.get_content_type() == "multipart/alternative"
    assert [part.get_content_type() for part in message.get_payload()] == [
        "text/plain",
        "text/html",
    ]
    smtp.close.assert_called_once()


async def test_cancellation_closes_smtp_without_retry() -> None:
    smtp = smtp_client()
    smtp.send_message.side_effect = asyncio.CancelledError
    with patch("src.raid.aiosmtplib.SMTP", return_value=smtp) as factory:
        with pytest.raises(asyncio.CancelledError):
            await deliver()
    factory.assert_called_once()
    smtp.close.assert_called_once()
