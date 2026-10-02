import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Settings
from src.raid import DigestService, EmailDeliveryError, NoPostsError, UpstreamError


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        yield client


def test_health_and_lifespan_cleanup(settings: Settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        service = app.state.digest_service
        assert client.get("/health").json() == {"status": "ok"}
        assert not service.reddit.is_closed
        assert not service.llm.is_closed()
    assert service.reddit.is_closed
    assert service.llm.is_closed()
    assert not hasattr(app.state, "digest_service")


@pytest.mark.parametrize(
    "authorization", [None, "Bearer incorrect", "Basic dXNlcjpwYXNz"]
)
def test_digest_rejects_unauthorized_requests(
    client: TestClient, authorization: str | None
) -> None:
    with patch.object(DigestService, "send_digest", new_callable=AsyncMock) as send:
        response = client.post(
            "/digest", headers={"Authorization": authorization} if authorization else {}
        )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    send.assert_not_awaited()


def test_digest_requires_post(client: TestClient) -> None:
    with patch.object(DigestService, "send_digest", new_callable=AsyncMock) as send:
        assert client.get("/digest").status_code == 405
    send.assert_not_awaited()


def test_digest_fails_closed_without_api_token(settings: Settings) -> None:
    settings.digest_api_token = None
    with TestClient(create_app(settings)) as client:
        assert client.post("/digest").status_code == 503


def test_digest_returns_typed_success(client: TestClient) -> None:
    with patch.object(
        DigestService, "send_digest", new_callable=AsyncMock, return_value=3
    ):
        response = client.post(
            "/digest", headers={"Authorization": "Bearer test-digest-token"}
        )
    assert response.status_code == 200
    assert response.json() == {"message": "Digest email sent successfully!", "posts": 3}
    schema = client.get("/openapi.json").json()
    assert "get" not in schema["paths"]["/digest"]
    assert schema["paths"]["/digest"]["post"]["security"] == [{"HTTPBearer": []}]


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (NoPostsError("No posts"), 400),
        (UpstreamError("Provider failed"), 502),
        (EmailDeliveryError("Delivery failed"), 502),
        (TimeoutError(), 504),
    ],
)
def test_digest_translates_failures(
    client: TestClient, failure: Exception, status: int
) -> None:
    with patch.object(
        DigestService, "send_digest", new_callable=AsyncMock, side_effect=failure
    ):
        response = client.post(
            "/digest", headers={"Authorization": "Bearer test-digest-token"}
        )
    assert response.status_code == status
    assert not client.app.state.digest_service.lock.locked()


async def test_overlapping_requests_are_rejected(settings: Settings) -> None:
    app = create_app(settings)
    started, release = asyncio.Event(), asyncio.Event()

    async def blocked_send(*args: object, **kwargs: object) -> int:
        started.set()
        await release.wait()
        return 1

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            with patch.object(DigestService, "send_digest", side_effect=blocked_send):
                headers = {"Authorization": "Bearer test-digest-token"}
                first = asyncio.create_task(client.post("/digest", headers=headers))
                try:
                    await asyncio.wait_for(started.wait(), timeout=1)
                    second = await client.post("/digest", headers=headers)
                    assert second.status_code == 409
                finally:
                    release.set()
                    response = await first
                assert response.status_code == 200
