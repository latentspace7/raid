import logging
from typing import Annotated, Literal, Self

from dotenv import load_dotenv
from pydantic import (
    AliasChoices,
    Field,
    HttpUrl,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

NonEmptySecret = Annotated[SecretStr, Field(min_length=1)]
EmailAddress = Annotated[str, Field(pattern=r"^[^\s@<>,]+@[^\s@<>,]+\.[^\s@<>,]+$")]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", populate_by_name=True, hide_input_in_errors=True
    )

    client_id: NonEmptySecret
    client_secret: NonEmptySecret
    gmail_email: EmailAddress
    gmail_app_password: NonEmptySecret
    to_email: EmailAddress
    openai_api_key: NonEmptySecret | None = Field(
        default=None, validation_alias=AliasChoices("OPENAI_API_KEY", "OPEN_AI_TOKEN")
    )
    openai_base_url: HttpUrl = HttpUrl("https://api.openai.com/v1")
    openai_model: str = Field(default="gpt-5-nano-2025-08-07", min_length=1)
    reddit_user_agent: str = Field(
        default="python:reddit-ai-digest:0.1.0", min_length=1
    )
    digest_api_token: NonEmptySecret | None = None
    digest_timeout_seconds: float = Field(default=300, gt=0, le=3600)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_openai_credentials(self) -> Self:
        if self.openai_base_url.host == "api.openai.com" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI API")
        if self.openai_base_url.username or self.openai_base_url.password:
            raise ValueError("OPENAI_BASE_URL must not contain credentials")
        return self


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        fields = sorted(
            {
                ".".join(map(str, error["loc"])) or "OpenAI settings"
                for error in exc.errors()
            }
        )
        raise ValueError(f"Invalid configuration: {', '.join(fields)}") from None


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
