import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from openai import AsyncOpenAI

from src.config import Settings
from src.models import RedditPost
from src.raid import (
    MAX_CONCURRENCY,
    UpstreamError,
    fetch_multiple_subreddits,
    get_llm_summaries_in_batches,
    normalize_reddit_post,
    open_digest_service,
)


def post_payload() -> dict[str, object]:
    return {
        "title": "Source title",
        "subreddit": "Python",
        "permalink": "/r/Python/comments/abc/source/",
        "score": 10,
    }


def post() -> RedditPost:
    result = normalize_reddit_post(post_payload())
    assert result is not None
    return result


def summary(link: str = "https://reddit.com/r/Python/comments/abc/source/") -> str:
    return f"[SUBREDDIT: Invented]\n[TITLE: Invented]\n[LINK: {link}]\n[SUMMARY: Useful summary.]\n[END]"


async def test_reddit_keeps_valid_posts_after_bad_records_and_partial_failure(
    settings: Settings,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "test-token"})
        assert request.headers["Authorization"] == "Bearer test-token"
        if request.url.path.endswith("new.json"):
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "data": {
                    "children": [
                        {"data": {**post_payload(), "score": "not-an-integer"}},
                        {"data": post_payload()},
                        {"data": post_payload()},
                    ]
                }
            },
        )

    async with httpx.AsyncClient(
        base_url="https://oauth.reddit.com", transport=httpx.MockTransport(handler)
    ) as client:
        posts = await fetch_multiple_subreddits(
            ["Python"], reddit_client=client, settings=settings
        )
    assert len(posts) == 1
    assert posts[0]["title"] == "Source title"


@pytest.mark.parametrize(
    "payload", [[], {"data": []}, {"data": {"children": "invalid"}}]
)
async def test_malformed_reddit_listings_are_errors(
    settings: Settings, payload: object
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"access_token": "test-token"}
            if request.method == "POST"
            else payload,
        )

    async with httpx.AsyncClient(
        base_url="https://oauth.reddit.com", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(UpstreamError, match="All Reddit listings failed"):
            await fetch_multiple_subreddits(
                ["Python"], reddit_client=client, settings=settings
            )


async def test_reddit_auth_failure_propagates(settings: Settings) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(401))
    ) as client:
        with pytest.raises(UpstreamError, match="authentication"):
            await fetch_multiple_subreddits(
                ["Python"], reddit_client=client, settings=settings
            )


async def test_llm_bounds_concurrency_and_keeps_partial_successes() -> None:
    active = peak = calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak, calls
        active += 1
        calls += 1
        request_number = calls
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        if request_number == 1:
            return httpx.Response(500, json={"error": {"message": "Temporary failure"}})
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 0,
                "model": "test-model",
                "status": "completed",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": summary(),
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    async with AsyncOpenAI(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    ) as client:
        result = await get_llm_summaries_in_batches(
            [post()] * 10, 1, client=client, model="test-model"
        )
    assert calls == 10
    assert peak == MAX_CONCURRENCY
    assert result.count("[END]") == 9


async def test_all_llm_failures_are_errors() -> None:
    async with AsyncOpenAI(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(401, json={"error": {"message": "Invalid"}})
            )
        ),
    ) as client:
        with pytest.raises(UpstreamError, match="All summarization batches failed"):
            await get_llm_summaries_in_batches(
                [post()], client=client, model="test-model"
            )


@pytest.mark.parametrize(
    "output",
    [
        "",
        "unparseable",
        summary("javascript:alert(1)"),
        summary("https://example.com/invented"),
    ],
)
async def test_unusable_summaries_never_send_email(
    settings: Settings, output: str
) -> None:
    async with open_digest_service(settings) as service:
        with (
            patch(
                "src.raid.fetch_multiple_subreddits",
                new_callable=AsyncMock,
                return_value=[post()],
            ),
            patch(
                "src.raid.get_llm_summaries_in_batches",
                new_callable=AsyncMock,
                return_value=output,
            ),
            patch("src.raid.send_email", new_callable=AsyncMock) as send,
        ):
            with pytest.raises(UpstreamError, match="no usable summaries"):
                await service.send_digest(["Python"], 3, 8)
            send.assert_not_awaited()


async def test_digest_uses_source_metadata_and_deduplicates(settings: Settings) -> None:
    async with open_digest_service(settings) as service:
        with (
            patch(
                "src.raid.fetch_multiple_subreddits",
                new_callable=AsyncMock,
                return_value=[post()],
            ),
            patch(
                "src.raid.get_llm_summaries_in_batches",
                new_callable=AsyncMock,
                return_value=summary() + "\n" + summary(),
            ),
            patch(
                "src.raid.send_email", new_callable=AsyncMock, return_value=True
            ) as send,
        ):
            assert await service.send_digest(["Python"], 3, 8) == 1
    plain_text = send.call_args.args[2]
    assert "[r/Python] Source title" in plain_text
    assert "Invented" not in plain_text


async def test_deadline_cancels_work_and_closes_clients(settings: Settings) -> None:
    settings.digest_timeout_seconds = 0.01
    cancelled = asyncio.Event()

    async def slow_fetch(*args: object, **kwargs: object) -> list[RedditPost]:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return []

    with patch("src.raid.fetch_multiple_subreddits", side_effect=slow_fetch):
        async with open_digest_service(settings) as service:
            with pytest.raises(TimeoutError):
                await service.send_digest(["Python"], 3, 8)
    assert cancelled.is_set()
    assert service.reddit.is_closed
    assert service.llm.is_closed()
