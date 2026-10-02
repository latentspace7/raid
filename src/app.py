import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .config import Settings, configure_logging, load_settings
from .raid import (
    API_SUBREDDITS,
    DigestService,
    EmailDeliveryError,
    NoPostsError,
    UpstreamError,
    open_digest_service,
)

bearer = HTTPBearer(auto_error=False)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class DigestResponse(BaseModel):
    message: str
    posts: int


def get_service(request: Request) -> DigestService:
    service = getattr(request.app.state, "digest_service", None)
    if not isinstance(service, DigestService):
        raise HTTPException(status_code=503, detail="Digest service is unavailable")
    return service


async def authorize_digest(
    service: Annotated[DigestService, Depends(get_service)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    token = service.settings.digest_api_token
    if token is None:
        raise HTTPException(
            status_code=503, detail="Digest API authentication is not configured"
        )
    if credentials is None or not hmac.compare_digest(
        credentials.credentials.encode(), token.get_secret_value().encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configured = settings if settings is not None else load_settings()
        configure_logging(configured)
        async with open_digest_service(configured) as service:
            app.state.digest_service = service
            try:
                yield
            finally:
                del app.state.digest_service

    application = FastAPI(title="Reddit AI Digest", lifespan=lifespan)

    @application.get("/health")
    async def health() -> HealthResponse:
        return HealthResponse()

    @application.post(
        "/digest",
        dependencies=[Depends(authorize_digest)],
        responses={
            400: {"description": "No posts available"},
            401: {"description": "Invalid or missing bearer token"},
            409: {"description": "A digest is already running in this worker"},
            502: {"description": "Provider or email delivery failure"},
            503: {"description": "Digest service is unavailable"},
            504: {"description": "Digest deadline exceeded; delivery may be unknown"},
        },
    )
    async def generate_digest(
        service: Annotated[DigestService, Depends(get_service)],
    ) -> DigestResponse:
        if service.lock.locked():
            raise HTTPException(status_code=409, detail="A digest is already running")
        try:
            async with service.lock:
                count = await service.send_digest(API_SUBREDDITS, 6, 10)
        except NoPostsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (UpstreamError, EmailDeliveryError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(
                status_code=504,
                detail="Digest timed out; check delivery before retrying",
            ) from exc
        return DigestResponse(message="Digest email sent successfully!", posts=count)

    return application


app = create_app()
