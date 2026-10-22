from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from html import escape
from urllib.parse import quote, urlsplit

SummaryPost = Mapping[str, object]

CANVAS = "#e9e6df"
PAPER = "#fffdf5"
SURFACE = "#ffffff"
INK = "#171717"
MUTED = "#48483f"
YELLOW = "#ffe34d"
MINT = "#b9f6cf"
LILAC = "#d7c6ff"
PINK = "#ffbbd1"
MONO = "'Courier New', Courier, monospace"


def _safe(value: object) -> str:
    return escape(str(value if value is not None else ""), quote=True)


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


def _render_stat(label: str, value: object, color: str) -> str:
    return f"""
        <td width="33.33%" valign="top" style="padding: 0 4px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background: {color}; border: 2px solid {INK};">
                <tr>
                    <td style="padding: 14px 4px; text-align: center; color: {INK};">
                        <div style="font-size: 30px; line-height: 34px; font-weight: 900;">{_safe(value)}</div>
                        <div style="padding-top: 4px; font-family: {MONO}; font-size: 10px; line-height: 16px; font-weight: 700; text-transform: uppercase;">{_safe(label)}</div>
                    </td>
                </tr>
            </table>
        </td>
    """


def _render_post(post: SummaryPost, number: int) -> str:
    return f"""
        <tr>
            <td class="post-padding" style="padding: 24px; border-top: 2px solid {INK}; background: {SURFACE};">
                <div style="margin-bottom: 12px; font-family: {MONO}; font-size: 11px; line-height: 16px; font-weight: 700; color: {MUTED};">THREAD / {number:02d}</div>
                <h3 style="margin: 0; font-size: 21px; line-height: 27px; font-weight: 800; overflow-wrap: anywhere; word-wrap: break-word;">
                    <a href="{_safe_link(post.get("link"))}" target="_blank" rel="noopener noreferrer" style="color: {INK}; text-decoration: none;">{_safe(post.get("title"))}</a>
                </h3>
                <p style="margin: 12px 0 20px; color: {MUTED}; font-size: 15px; line-height: 24px; overflow-wrap: anywhere; word-wrap: break-word;">{_safe(post.get("summary"))}</p>
                <table role="presentation" cellspacing="0" cellpadding="0">
                    <tr>
                        <td bgcolor="{YELLOW}" style="background: {YELLOW}; border: 2px solid {INK}; box-shadow: 3px 3px 0 {INK};">
                            <a href="{_safe_link(post.get("link"))}" target="_blank" rel="noopener noreferrer" style="display: inline-block; padding: 12px 16px; color: {INK}; font-family: {MONO}; font-size: 12px; line-height: 18px; font-weight: 700; text-decoration: none;">OPEN THREAD &rarr;</a>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    """


def _render_subreddit_section(
    subreddit: str, posts: list[SummaryPost], first_number: int, color: str
) -> str:
    rendered_posts = "".join(
        _render_post(post, first_number + index) for index, post in enumerate(posts)
    )
    return f"""
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin: 0 0 26px; table-layout: fixed; background: {SURFACE}; border: 3px solid {INK}; box-shadow: 5px 5px 0 {INK};">
            <tr>
                <td class="section-heading" style="padding: 16px 20px; background: {color}; color: {INK};">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="table-layout: fixed;">
                        <tr>
                            <td style="overflow-wrap: anywhere; word-wrap: break-word;"><h2 style="margin: 0; font-size: 19px; line-height: 25px; font-weight: 800;">r/{_safe(subreddit)}</h2></td>
                            <td width="66" align="right" style="font-family: {MONO}; font-size: 11px; line-height: 16px; font-weight: 700;">{len(posts)} {"POST" if len(posts) == 1 else "POSTS"}</td>
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
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom: 26px; background: {YELLOW}; border: 3px solid {INK}; box-shadow: 5px 5px 0 {INK};">
            <tr>
                <td style="padding: 22px; color: {INK};">
                    <div style="font-family: {MONO}; font-size: 11px; line-height: 16px; font-weight: 700;">KEEP EXPLORING</div>
                    <div style="padding-top: 8px; font-size: 21px; line-height: 28px; font-weight: 800;">{remaining} more {"post" if remaining == 1 else "posts"} not shown</div>
                    <a href="https://reddit.com/r/{reddit_path}" target="_blank" rel="noopener noreferrer" style="display: inline-block; padding: 14px 0 4px; color: {INK}; font-size: 14px; line-height: 22px; font-weight: 700; text-decoration: underline;">View all on Reddit &rarr;</a>
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

        colors = (MINT, LILAC, PINK)
        sections.append(
            _render_subreddit_section(
                subreddit,
                visible_posts,
                posts_shown + 1,
                colors[len(sections) % len(colors)],
            )
        )
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
    current_date = datetime.now().strftime("%d %b %Y").upper()
    subreddit_summary = ", ".join(f"r/{sub}" for sub in subreddit_list)
    post_sections = _render_post_sections(posts_data, subreddit_list, max_display)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light">
    <meta name="supported-color-schemes" content="light">
    <title>RAID — Reddit AI Digest</title>
    <style>
        body {{ -webkit-text-size-adjust: 100%; }}
        table {{ border-spacing: 0; }}
        @media only screen and (max-width: 480px) {{
            .outer-padding {{ padding: 16px 12px 24px !important; }}
            .masthead-padding {{ padding: 24px 18px !important; }}
            .hero-title {{ font-size: 40px !important; line-height: 40px !important; letter-spacing: -2px !important; }}
            .content-padding {{ padding: 24px 12px 4px !important; }}
            .post-padding {{ padding: 20px 16px !important; }}
            .section-heading {{ padding: 14px 12px !important; }}
            .footer-padding {{ padding: 24px 18px !important; }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; background: {CANVAS}; color: {INK}; font-family: Arial, Helvetica, sans-serif;">
    <div aria-hidden="true" style="display: none; overflow: hidden; line-height: 1px; opacity: 0; max-height: 0; max-width: 0; mso-hide: all;">
        {_safe(len(posts_data))} Reddit summaries from {_safe(len(subreddit_list))} subreddits.
    </div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background: {CANVAS};">
        <tr>
            <td class="outer-padding" align="center" style="padding: 36px 20px 44px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 680px; table-layout: fixed; background: {PAPER}; border: 3px solid {INK}; box-shadow: 8px 8px 0 {INK};">
                    <tr>
                        <td class="masthead-padding" style="padding: 28px 30px 32px; background: {YELLOW}; color: {INK}; border-bottom: 3px solid {INK};">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="font-family: {MONO}; font-size: 12px; line-height: 18px; font-weight: 700; letter-spacing: 1px;">RAID / DAILY</td>
                                    <td align="right" style="font-family: {MONO}; font-size: 11px; line-height: 18px; font-weight: 700;">{_safe(current_date)}</td>
                                </tr>
                            </table>
                            <h1 class="hero-title" style="margin: 28px 0 18px; font-family: 'Arial Black', Arial, Helvetica, sans-serif; font-size: 58px; line-height: 56px; letter-spacing: -3px; font-weight: 900;">YOUR DAILY<br>REDDIT RAID.</h1>
                            <p style="margin: 0; font-size: 15px; line-height: 23px;">The threads. The ideas. The quick version.</p>
                        </td>
                    </tr>
                    <tr>
                        <td class="content-padding" style="padding: 28px 26px 4px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="table-layout: fixed;">
                                <tr>
                                    {_render_stat("posts", len(posts_data), SURFACE)}
                                    {_render_stat("subreddits", len(subreddit_list), LILAC)}
                                    {_render_stat("shown", min(len(posts_data), max_display), MINT)}
                                </tr>
                            </table>
                            <div style="margin: 22px 4px 24px; padding-bottom: 20px; border-bottom: 2px solid {INK}; color: {MUTED}; font-family: {MONO}; font-size: 11px; line-height: 19px; overflow-wrap: anywhere; word-wrap: break-word;">
                                <strong style="color: {INK};">ON THE RADAR</strong><br>{_safe(subreddit_summary)}
                            </div>
                            {post_sections}
                        </td>
                    </tr>
                    <tr>
                        <td class="footer-padding" style="padding: 26px 30px; background: {INK}; color: {PAPER};">
                            <div style="font-size: 23px; line-height: 29px; font-weight: 900;">YOU'RE ALL CAUGHT UP.</div>
                            <p style="margin: 12px 0 16px; font-size: 12px; line-height: 20px;">Reddit AI Digest &middot; Reddit threads, condensed by AI.<br>Follow a thread to read the full conversation.</p>
                            <div style="font-family: {MONO}; font-size: 12px; line-height: 20px; font-weight: 700;">
                                <a href="https://reddit.com" target="_blank" rel="noopener noreferrer" style="display: inline-block; padding: 8px 0; color: {MINT}; text-decoration: underline;">BACK TO REDDIT &rarr;</a>
                            </div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
