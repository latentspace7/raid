from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class RedditPost(TypedDict):
    title: str
    author: str
    score: int
    num_comments: int
    created_utc: float
    subreddit: str
    permalink: str
    url: str
    is_self: bool
    selftext: str
    upvote_ratio: float
    content_type: Literal["text", "link"]
    content: str


class SummaryPost(TypedDict):
    subreddit: str
    title: str
    link: str
    summary: str


class RedditPostPayload(BaseModel):
    model_config = ConfigDict(
        strict=True, str_strip_whitespace=True, allow_inf_nan=False
    )

    title: str = Field(min_length=1)
    permalink: str = Field(pattern=r"^/r/[A-Za-z0-9_]+/comments/[^\s]+$")
    subreddit: str = Field(pattern=r"^[A-Za-z0-9_]+$")
    author: str | None = None
    score: int = 0
    num_comments: int = Field(default=0, ge=0)
    created_utc: float = Field(default=0, ge=0)
    url: str = ""
    is_self: bool = False
    selftext: str = ""
    upvote_ratio: float = Field(default=0, ge=0, le=1)
    stickied: bool = False


class RedditListingChild(BaseModel):
    data: dict[str, object]


class RedditListingData(BaseModel):
    children: list[RedditListingChild]


class RedditListing(BaseModel):
    data: RedditListingData


class RedditToken(BaseModel):
    access_token: Annotated[str, Field(min_length=1)]
