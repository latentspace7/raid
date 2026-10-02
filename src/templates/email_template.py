from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from html import escape
from urllib.parse import quote, urlsplit

SummaryPost = Mapping[str, object]

CANVAS = "#edf4f8"
SURFACE = "#ffffff"
SURFACE_TINT = "#f7fbff"
POST_SURFACE = "#f1f6fb"
POST_SURFACE_ALT = "#ecf3f9"
INK = "#132238"
INK_SOFT = "#1f3550"
MUTED = "#607086"
MUTED_STRONG = "#53687f"
BORDER = "#d7e3ee"
HEADER_BG = "#17324d"
HEADER_TEXT = "#f8fbff"
HEADER_MUTED = "#c7d7e6"
PRIMARY = "#1d5fd0"
PRIMARY_DARK = "#123e7c"
PRIMARY_SOFT = "#eaf3ff"
ACCENT = "#f97316"
ACCENT_SOFT = "#fff3e6"
ACCENT_TEXT = "#8a3a0a"
TEAL = "#0f766e"
TEAL_SOFT = "#e6f7f4"


def _safe(value: object) -> str:
    return escape(str(value or ""), quote=True)


def _safe_link(value: object) -> str:
    if not isinstance(value, str) or any(character.isspace() for character in value):
        return "#"
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return "#"
    except ValueError:
        return "#"
    return _safe(value)


def _render_stat(label: str, value: object) -> str:
    return f"""
        <td style="padding: 0 6px 12px 6px;" width="33.33%">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background: {PRIMARY_SOFT}; border: 1px solid #c8dcf4; border-radius: 8px;">
                <tr>
                    <td style="padding: 14px 12px; text-align: center;">
                        <div style="font-size: 20px; line-height: 24px; font-weight: 700; color: {PRIMARY_DARK};">{_safe(value)}</div>
                        <div style="font-size: 12px; line-height: 16px; color: {MUTED}; text-transform: uppercase; letter-spacing: 0.04em;">{_safe(label)}</div>
                    </td>
                </tr>
            </table>
        </td>
    """


def _render_post(post: SummaryPost) -> str:
    return f"""
        <tr>
            <td style="padding: 16px 18px; border-top: 1px solid {BORDER}; background: {POST_SURFACE};">
                <a href="{_safe_link(post.get("link"))}" target="_blank" rel="noopener noreferrer" style="color: {INK_SOFT}; font-size: 15px; line-height: 21px; font-weight: 700; text-decoration: none;">{_safe(post.get("title"))}</a>
                <div style="padding-top: 7px; color: {MUTED_STRONG}; font-size: 13px; line-height: 20px;">{_safe(post.get("summary"))}</div>
                <div style="padding-top: 10px;">
                    <a href="{_safe_link(post.get("link"))}" target="_blank" rel="noopener noreferrer" style="color: {PRIMARY}; font-size: 12px; line-height: 16px; font-weight: 700; text-decoration: none;">Open thread</a>
                </div>
            </td>
        </tr>
    """


def _render_subreddit_section(subreddit: str, posts: list[SummaryPost]) -> str:
    rendered_posts = "".join(
        _render_post(post).replace(
            POST_SURFACE, POST_SURFACE if index % 2 == 0 else POST_SURFACE_ALT
        )
        for index, post in enumerate(posts)
    )
    return f"""
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin: 0 0 18px 0; background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; overflow: hidden;">
            <tr>
                <td style="padding: 13px 18px; background: {TEAL_SOFT}; border-left: 4px solid {TEAL};">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                        <tr>
                            <td style="color: {PRIMARY_DARK}; font-size: 15px; line-height: 20px; font-weight: 800;">r/{_safe(subreddit)}</td>
                            <td align="right" style="color: {TEAL}; font-size: 12px; line-height: 16px; font-weight: 700;">{len(posts)} posts</td>
                        </tr>
                    </table>
                </td>
            </tr>
            {rendered_posts}
        </table>
    """


def _render_more_link(remaining: int, subreddit_list: list[str]) -> str:
    reddit_path = "+".join(quote(subreddit, safe="") for subreddit in subreddit_list)
    return f"""
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background: {PRIMARY_SOFT}; border: 1px solid #c8dcf4; border-radius: 8px;">
            <tr>
                <td style="padding: 18px; text-align: center;">
                    <div style="color: {PRIMARY_DARK}; font-size: 14px; line-height: 20px; font-weight: 700;">{remaining} more posts not shown</div>
                    <div style="padding-top: 8px;">
                        <a href="https://reddit.com/r/{reddit_path}" target="_blank" style="color: {PRIMARY}; font-size: 13px; line-height: 18px; font-weight: 700; text-decoration: none;">View all on Reddit</a>
                    </div>
                </td>
            </tr>
        </table>
    """


def _render_post_sections(
    posts_data: Sequence[SummaryPost], subreddit_list: list[str], max_display: int
) -> str:
    posts_by_subreddit: dict[str, list[SummaryPost]] = defaultdict(list)
    for post in posts_data:
        posts_by_subreddit[str(post.get("subreddit", ""))].append(post)

    sorted_subreddits = sorted(
        posts_by_subreddit.items(), key=lambda item: len(item[1]), reverse=True
    )

    sections: list[str] = []
    posts_shown = 0

    for subreddit, posts in sorted_subreddits:
        if posts_shown >= max_display:
            break

        remaining_slots = max_display - posts_shown
        visible_posts = posts[:remaining_slots]
        if not visible_posts:
            continue

        sections.append(_render_subreddit_section(subreddit, visible_posts))
        posts_shown += len(visible_posts)

    if len(posts_data) > posts_shown:
        sections.append(
            _render_more_link(len(posts_data) - posts_shown, subreddit_list)
        )

    return "".join(sections)


def generate_email_template(
    posts_data: Sequence[SummaryPost], subreddit_list: list[str], max_display: int = 15
) -> str:
    if max_display < 1:
        raise ValueError("max_display must be positive")
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    subreddit_summary = ", ".join(f"r/{sub}" for sub in subreddit_list)
    post_sections = _render_post_sections(posts_data, subreddit_list, max_display)

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit Daily Digest</title>
</head>
<body style="margin: 0; padding: 0; background: {CANVAS}; color: {INK}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;">
    <div style="display: none; overflow: hidden; line-height: 1px; opacity: 0; max-height: 0; max-width: 0;">
        {_safe(len(posts_data))} Reddit summaries from {_safe(len(subreddit_list))} subreddits.
    </div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background: {CANVAS};">
        <tr>
            <td align="center" style="padding: 28px 12px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 680px; background: {SURFACE}; border-radius: 12px; overflow: hidden; border: 1px solid {BORDER};">
                    <tr>
                        <td style="padding: 30px 28px; background: {HEADER_BG}; border-bottom: 4px solid {ACCENT};">
                            <div style="color: {ACCENT}; font-size: 12px; line-height: 16px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em;">Reddit AI Digest</div>
                            <h1 style="margin: 8px 0 0 0; color: {HEADER_TEXT}; font-size: 28px; line-height: 34px; font-weight: 800;">Today's Reddit signal</h1>
                            <div style="padding-top: 10px; color: {HEADER_MUTED}; font-size: 14px; line-height: 20px;">{_safe(current_date)}</div>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 24px 22px 8px 22px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    {_render_stat("posts", len(posts_data))}
                                    {_render_stat("subreddits", len(subreddit_list))}
                                    {_render_stat("shown", min(len(posts_data), max_display))}
                                </tr>
                            </table>
                            <div style="margin: 0 6px 20px 6px; padding: 14px 16px; background: {ACCENT_SOFT}; border-left: 4px solid {ACCENT}; border-radius: 6px; color: {ACCENT_TEXT}; font-size: 13px; line-height: 20px;">
                                Tracking {_safe(subreddit_summary)}.
                            </div>
                            {post_sections}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 20px 28px; background: {SURFACE_TINT}; color: {MUTED}; font-size: 12px; line-height: 18px; text-align: center;">
                            Generated from Reddit API data and OpenAI summaries.
                            <div style="padding-top: 8px;">
                                <a href="https://reddit.com" target="_blank" style="color: {PRIMARY}; font-weight: 700; text-decoration: none;">Visit Reddit</a>
                            </div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
