import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from raid import create_condensed_html_email, parse_summaries


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


def test_create_condensed_html_email_respects_max_display_not_five_per_subreddit() -> None:
    posts_data = [
        {
            "subreddit": "Python",
            "title": f"Post {index}",
            "link": f"https://reddit.com/{index}",
            "summary": f"Summary {index}",
        }
        for index in range(1, 9)
    ]

    html = create_condensed_html_email(posts_data, ["Python"], max_display=8)

    assert html.count('class="post-item"') == 8
    assert "Post 8" in html
