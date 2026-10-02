import pytest

from src.raid import (
    create_condensed_html_email,
    create_plain_text_email,
    normalize_reddit_post,
    parse_summaries,
)


def test_parse_summaries_recovers_trailing_post_missing_end_marker() -> None:
    # Simulates model output truncated mid-batch: last thread has no [END].
    summary_text = """
    [SUBREDDIT: Python]
    [TITLE: First post]
    [LINK: https://reddit.com/1]
    [SUMMARY: First summary.]
    [END]
    [SUBREDDIT: Python]
    [TITLE: Truncated post]
    [LINK: https://reddit.com/2]
    [SUMMARY: Second summary that got cut
    """

    posts = parse_summaries(summary_text)

    assert len(posts) == 2
    assert posts[0]["title"] == "First post"
    assert posts[1]["title"] == "Truncated post"


def test_parse_summaries_returns_all_well_formed_posts() -> None:
    summary_text = """
    [SUBREDDIT: Python]
    [TITLE: First post]
    [LINK: https://reddit.com/1]
    [SUMMARY: First summary.]
    [END]
    [SUBREDDIT: Python]
    [TITLE: Second post]
    [LINK: https://reddit.com/2]
    [SUMMARY: Second summary.]
    [END]
    """

    posts = parse_summaries(summary_text)

    assert len(posts) == 2
    assert posts[0]["title"] == "First post"
    assert posts[1]["title"] == "Second post"


def test_condensed_html_respects_max_display() -> None:
    posts_data = [
        {
            "subreddit": "Python",
            "title": f"Post {index}",
            "link": f"https://reddit.com/{index}",
            "summary": f"Summary {index}",
        }
        for index in range(1, 11)
    ]

    html = create_condensed_html_email(posts_data, ["Python"], max_display=8)

    assert "Post 8" in html
    assert "Post 9" not in html
    assert "2 more posts not shown" in html


def test_normalize_reddit_post_skips_stickied_posts() -> None:
    assert normalize_reddit_post({"stickied": True}) is None


def test_normalize_reddit_post_builds_link_content() -> None:
    post = normalize_reddit_post(
        {
            "title": "HTTPX release",
            "author": "example",
            "score": 42,
            "num_comments": 7,
            "created_utc": 1710000000,
            "subreddit": "Python",
            "permalink": "/r/Python/comments/abc/httpx_release/",
            "url": "https://example.com/httpx",
            "is_self": False,
            "upvote_ratio": 0.95,
        }
    )

    assert post is not None
    assert post["content_type"] == "link"
    assert post["content"] == "External link to: https://example.com/httpx"


def test_create_plain_text_email_uses_shared_digest_format() -> None:
    plain_text = create_plain_text_email(
        [
            {
                "subreddit": "Python",
                "title": "Post",
                "link": "https://reddit.com/1",
                "summary": "Summary.",
            }
        ],
        subreddit_count=1,
    )

    assert "Total posts: 1 from 1 subreddits" in plain_text
    assert "Link: https://reddit.com/1" in plain_text


@pytest.mark.parametrize(
    "link",
    [
        "javascript:alert(1)",
        "data:text/html,evil",
        "//evil.example",
        "https://user:password@example.com",
    ],
)
def test_email_escapes_text_and_rejects_unsafe_links(link: str) -> None:
    html = create_condensed_html_email(
        [
            {
                "subreddit": "Python",
                "title": "<script>bad</script>",
                "summary": "<img src=x onerror=bad>",
                "link": link,
            }
        ],
        ["Python"],
    )
    assert "<script>" not in html
    assert "<img src=x" not in html
    assert 'href="#"' in html
    assert link not in html
