"""YouTube channel data collection via Playwright browser automation."""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_browsers_cache = Path.home() / ".cache" / "ms-playwright"
if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH") and _browsers_cache.exists():
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_browsers_cache)

from playwright.sync_api import Page

from agent.config import get_youtube_config, resolve_target_channel
from agent.custom_tools.comment_selection import is_channel_author_comment
from agent.custom_tools.browser_tools import (
    _dismiss_optional_screens,
    close_browser_session,
    ensure_youtube_session,
    navigate_to_channel,
    save_session,
)
from agent.custom_tools.video_info import (
    build_video_about_summary,
    extract_full_description,
    extract_player_metadata,
    merge_metadata_fields,
    merge_video_records,
)

COMMENT_THREAD_SELECTOR = (
    "ytd-comment-thread-renderer, ytd-comments#comments ytd-comment-thread-renderer"
)
COMMENT_DISABLED_TEXT = (
    "Comments are turned off",
    "Commenting is disabled",
    "Comments are disabled",
)
# Modern YouTube comment/reply UI (yt-button-shape + ytSpecButtonShapeNext*)
THREAD_REPLY_BUTTON_SELECTOR = (
    '#reply-button-end yt-button-shape button[aria-label="Reply"].ytSpecButtonShapeNextText, '
    '#reply-button-end yt-button-shape button[aria-label="Reply"]:not(.ytSpecButtonShapeNextCallToAction), '
    '#reply-button-end button[aria-label="Reply"]:not(.ytSpecButtonShapeNextCallToAction)'
)
REPLY_INPUT_SELECTOR = (
    'ytd-commentbox yt-formatted-string#contenteditable-textarea #contenteditable-root, '
    'ytd-commentbox #contenteditable-root[aria-label="Add a reply..."], '
    'ytd-commentbox #contenteditable-root[contenteditable="true"]'
)
SUBMIT_REPLY_BUTTON_SELECTOR = (
    'ytd-commentbox yt-button-shape button[aria-label="Reply"].ytSpecButtonShapeNextCallToAction, '
    'ytd-commentbox yt-button-shape button[aria-label="Reply"].ytSpecButtonShapeNextFilled, '
    'ytd-commentbox button.ytSpecButtonShapeNextCallToAction[aria-label="Reply"], '
    'ytd-commentbox #submit-button yt-button-shape button[aria-label="Reply"]'
)
SIMPLEBOX_PLACEHOLDER_SELECTOR = (
    "yt-formatted-string#simplebox-placeholder, "
    "#simplebox-placeholder, "
    'ytd-comment-simplebox-renderer yt-formatted-string[role="textbox"]'
)
VIDEO_COMMENT_INPUT_SELECTOR = (
    '#contenteditable-root[aria-label="Add a comment..."], '
    "ytd-comments-header-renderer #contenteditable-root[contenteditable='true'], "
    "ytd-comment-simplebox-renderer #contenteditable-root[contenteditable='true']"
)
VIDEO_COMMENT_SUBMIT_SELECTOR = (
    'yt-button-shape button[aria-label="Comment"].ytSpecButtonShapeNextCallToAction, '
    'yt-button-shape button[aria-label="Comment"].ytSpecButtonShapeNextFilled, '
    'button.ytSpecButtonShapeNextCallToAction[aria-label="Comment"], '
    '#submit-button yt-button-shape button[aria-label="Comment"]'
)

# Reused browser session between scrape and post steps (same video page).
_BROWSER_SESSION: dict[str, Any] = {}
_BLOCKED_POST_PHRASES = (
    "automated test",
    "agent diagnostic",
    "please ignore",
    "test comment from",
    "automation diagnostic",
)


def _is_blocked_post_text(text: str) -> bool:
    """Reject test/diagnostic phrasing that should never be posted publicly."""
    lowered = (text or "").lower()
    return any(phrase in lowered for phrase in _BLOCKED_POST_PHRASES)
_EXTRACT_COMMENTS_JS = """
(maxCount) => {
  const threads = document.querySelectorAll('ytd-comment-thread-renderer');
  const results = [];
  const limit = maxCount > 0 ? Math.min(threads.length, maxCount) : threads.length;

  for (let index = 0; index < limit; index++) {
    const thread = threads[index];
    const comment = thread.querySelector(
      'ytd-comment-view-model#comment, ytd-comment-view-model'
    );
    if (!comment) continue;

    const authorEl = comment.querySelector(
      '#author-text span, a#author-text span, yt-formatted-string#author-text, #header-author a'
    );
    const author = (authorEl?.innerText || authorEl?.textContent || '').trim();

    const textEl = comment.querySelector(
      'yt-attributed-string#content-text, #content-text'
    );
    const text = (textEl?.innerText || textEl?.textContent || '').trim();
    if (!text) continue;

    const timeLink = comment.querySelector(
      '#published-time-text a, a.published-time-text'
    );
    const timestamp = (timeLink?.innerText || timeLink?.textContent || '').trim();
    let youtubeCommentId = '';
    const href = timeLink?.getAttribute('href') || '';
    const lcMatch = href.match(/[?&]lc=([^&]+)/);
    if (lcMatch) youtubeCommentId = lcMatch[1];

    const voteEl = comment.querySelector('#vote-count-middle');
    let likesRaw = (voteEl?.innerText || voteEl?.textContent || '').trim();
    if (!likesRaw) {
      const likeBtn = comment.querySelector('#like-button button[aria-label]');
      const label = likeBtn?.getAttribute('aria-label') || '';
      const match = label.match(/(\\d[\\d,]*)/);
      if (match) likesRaw = match[1];
    }

    const isPinned = !!comment.querySelector(
      '#pinned-comment-badge, ytd-pinned-comment-badge-renderer'
    );
    // Channel-owner badge is resolved server-side from author vs channel name.
    // ytd-author-comment-badge-renderer also matches member/verified badges.
    const isChannelOwner = false;

    const repliesSection = thread.querySelector('ytd-comment-replies-renderer');
    let channelReplied = false;
    if (repliesSection) {
      const ownerReply = repliesSection.querySelector(
        'ytd-comment-view-model ytd-author-comment-badge-renderer, ' +
        'ytd-comment-renderer ytd-author-comment-badge-renderer'
      );
      channelReplied = !!ownerReply;
    }

    results.push({
      author,
      text,
      timestamp,
      likes_raw: likesRaw,
      youtube_comment_id: youtubeCommentId,
      is_pinned: isPinned,
      is_channel_owner: isChannelOwner,
      channel_replied: channelReplied,
      thread_index: index,
    });
  }
  return results;
}
"""


def _extract_channel_id(url: str) -> str:
    """Extract channel identifier from a YouTube channel URL."""
    if "/channel/" in url:
        return url.split("/channel/")[1].split("/")[0].split("?")[0]
    if "/@" in url:
        return url.split("/@")[1].split("/")[0].split("?")[0]
    if "/c/" in url:
        return url.split("/c/")[1].split("/")[0].split("?")[0]
    return urlparse(url).path.strip("/").replace("/", "_") or "unknown"


def _extract_channel_name(page: Page) -> str:
    """Read channel display name from the channel page."""
    selectors = [
        "yt-formatted-string#text.ytd-channel-name",
        "#channel-name #text",
        "ytd-channel-name #text",
        "#inner-header-container #text",
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=2000):
                text = locator.inner_text().strip()
                if text:
                    return text
        except Exception:
            continue
    title = page.title()
    return title.replace(" - YouTube", "").strip() or "Unknown Channel"


def _resolve_scrape_target(reported_count: int, max_comments: int) -> int:
    """Resolve how many comment threads to load (0 = all reported/visible)."""
    min_when_unlimited = 25
    if max_comments <= 0:
        if reported_count > 0:
            return max(reported_count, min_when_unlimited)
        return 500
    if reported_count > 0:
        return max(max_comments, reported_count)
    return max_comments


def _normalize_js_comment(
    raw: dict[str, Any],
    video: dict[str, str],
    channel_name: str = "",
) -> dict[str, Any]:
    """Convert a browser-extracted comment dict into workflow format."""
    thread_index = int(raw.get("thread_index", 0))
    youtube_comment_id = str(raw.get("youtube_comment_id") or "").strip()
    comment_id = youtube_comment_id or f"{video['video_id']}_{thread_index}"
    channel_replied = bool(raw.get("channel_replied"))
    author = raw.get("author") or "Unknown"
    return {
        "author": author,
        "text": raw.get("text") or "",
        "likes": _parse_likes(str(raw.get("likes_raw") or "")),
        "timestamp": raw.get("timestamp") or "",
        "replied": False,
        "agent_replied": False,
        "channel_replied": channel_replied,
        "is_pinned": bool(raw.get("is_pinned")),
        "is_channel_owner": is_channel_author_comment(
            {"author": author}, channel_name
        ),
        "video_id": video["video_id"],
        "video_title": video["title"],
        "video_url": video["url"],
        "comment_id": comment_id,
        "youtube_comment_id": youtube_comment_id,
        "thread_index": thread_index,
    }


def _parse_comment_count(text: str) -> int:
    """Parse total comment count from YouTube header text like '440 Comments'."""
    if not text:
        return 0
    match = re.search(r"([\d][\d,]*)", text.replace("\xa0", " "))
    if not match:
        return 0
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return 0


def _current_thread_id() -> int:
    return threading.get_ident()


def _session_owned_by_current_thread() -> bool:
    stored = _BROWSER_SESSION.get("thread_id")
    return stored is not None and int(stored) == _current_thread_id()


def _discard_cross_thread_session() -> None:
    """Drop stale Playwright handles created on another worker thread."""
    if _BROWSER_SESSION and not _session_owned_by_current_thread():
        _BROWSER_SESSION.clear()


def _store_browser_session(
    playwright: Any,
    browser: Any,
    context: Any,
    page: Page,
    video_url: str = "",
) -> None:
    """Keep the Playwright session alive for reply/comment posting on the same page."""
    _BROWSER_SESSION.clear()
    _BROWSER_SESSION.update(
        {
            "playwright": playwright,
            "browser": browser,
            "context": context,
            "page": page,
            "video_url": video_url,
            "thread_id": _current_thread_id(),
        }
    )


def release_browser_session() -> None:
    """Close and clear any stored Playwright session."""
    if not _BROWSER_SESSION:
        return
    if not _session_owned_by_current_thread():
        _BROWSER_SESSION.clear()
        return
    playwright = _BROWSER_SESSION.get("playwright")
    browser = _BROWSER_SESSION.get("browser")
    context = _BROWSER_SESSION.get("context")
    _BROWSER_SESSION.clear()
    close_browser_session(playwright, browser, context)


def _get_stored_page() -> Page | None:
    _discard_cross_thread_session()
    page = _BROWSER_SESSION.get("page")
    return page if page is not None else None


def _acquire_page_for_posting() -> tuple[Any, Any, Any, Page, bool, bool]:
    """Return (playwright, browser, context, page, logged_in, owns_session)."""
    stored_page = _get_stored_page()
    if stored_page is not None and _is_page_alive(stored_page):
        return (
            _BROWSER_SESSION.get("playwright"),
            _BROWSER_SESSION.get("browser"),
            _BROWSER_SESSION.get("context"),
            stored_page,
            True,
            False,
        )

    release_browser_session()
    playwright, browser, context, page, logged_in = ensure_youtube_session()
    return playwright, browser, context, page, logged_in, True


def prepare_browser_for_posting(video_url: str = "") -> tuple[Page | None, str]:
    """Ensure the Chrome tab stays open on the target video for posting."""
    _discard_cross_thread_session()
    config = get_youtube_config()
    target = (video_url or str(_BROWSER_SESSION.get("video_url") or "")).strip()

    page = _get_stored_page()
    if page is not None and _is_page_alive(page):
        if target:
            _ensure_page_on_video(page, target)
            _BROWSER_SESSION["video_url"] = target
        return page, ""

    playwright = browser = context = None
    owns_session = False
    try:
        playwright, browser, context, page, logged_in, owns_session = _acquire_page_for_posting()
        if not logged_in:
            return None, "Not logged in to YouTube"
        if target:
            _ensure_page_on_video(page, target)
        if config.get("keep_browser_open", True):
            _store_browser_session(playwright, browser, context, page, video_url=target)
        return page, ""
    except Exception as exc:
        if owns_session:
            close_browser_session(playwright, browser, context)
        return None, str(exc)


def _channel_videos_url(channel_url: str) -> str:
    """Normalize a channel URL to its Videos tab."""
    url = channel_url.rstrip("/")
    if any(
        url.endswith(suffix)
        for suffix in ("/videos", "/streams", "/shorts", "/playlists")
    ):
        return url
    return f"{url}/videos"


def _is_watch_video_href(href: str) -> bool:
    """Return True for standard watch URLs, excluding Shorts."""
    if not href or "/watch" not in href:
        return False
    return "/shorts/" not in href


def _collect_video_urls_via_script(page: Page, max_videos: int) -> list[dict[str, str]]:
    """Collect latest channel videos from modern YouTube lockup/grid markup."""
    try:
        entries = page.evaluate(
            """
            (maxVideos) => {
              const results = [];
              const seen = new Set();
              const selectors = [
                'a.ytLockupMetadataViewModelTitle[href*="/watch?v="]',
                'a.ytLockupViewModelContentImage[href*="/watch?v="]',
                'ytd-rich-item-renderer a[href*="/watch?v="]',
                'a#video-title-link[href*="/watch?v="]',
                'a#video-title[href*="/watch?v="]',
              ];

              const addEntry = (anchor) => {
                if (!anchor) return;
                const href = anchor.getAttribute('href') || '';
                if (!href.includes('/watch?v=') || href.includes('/shorts/')) return;
                const params = new URLSearchParams(href.split('?')[1] || '');
                const videoId = params.get('v');
                if (!videoId || seen.has(videoId)) return;
                seen.add(videoId);

                let title = (anchor.innerText || anchor.textContent || '').trim();
                if (!title) {
                  title = (anchor.getAttribute('aria-label') || '').trim();
                }
                title = title.replace(/\\s+\\d+ hours?,? \\d+ minutes?$/i, '').trim();

                const host = anchor.closest(
                  'yt-lockup-view-model, ytd-rich-item-renderer, ytd-rich-grid-media, ytd-grid-video-renderer'
                );
                let views = '';
                let published = '';
                let duration = '';
                if (host) {
                  const metaTexts = host.querySelectorAll(
                    '.ytContentMetadataViewModelMetadataText, #metadata-line span'
                  );
                  const values = Array.from(metaTexts)
                    .map((el) => (el.innerText || el.textContent || '').trim())
                    .filter(Boolean);
                  for (const value of values) {
                    const lower = value.toLowerCase();
                    if (!views && lower.includes('view')) views = value;
                    else if (!published && lower.includes('ago')) published = value;
                  }
                  const badge = host.querySelector('.ytBadgeShapeText, ytd-thumbnail-overlay-time-status-renderer span');
                  if (badge) {
                    duration = (badge.innerText || badge.textContent || '').trim();
                  }
                }

                results.push({
                  video_id: videoId,
                  title: title || `Video ${videoId}`,
                  url: `https://www.youtube.com/watch?v=${videoId}`,
                  views,
                  published,
                  duration,
                });
              };

              for (const selector of selectors) {
                for (const anchor of document.querySelectorAll(selector)) {
                  addEntry(anchor);
                  if (results.length >= maxVideos) return results;
                }
              }
              return results;
            }
            """,
            max_videos,
        )
    except Exception:
        return []

    if not isinstance(entries, list):
        return []

    videos: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("video_id", "")).strip()
        if not video_id:
            continue
        videos.append(
            {
                "video_id": video_id,
                "title": str(entry.get("title", "")).strip() or f"Video {video_id}",
                "url": str(entry.get("url", "")).strip()
                or f"https://www.youtube.com/watch?v={video_id}",
                **({"views": entry["views"]} if entry.get("views") else {}),
                **({"published": entry["published"]} if entry.get("published") else {}),
                **({"duration": entry["duration"]} if entry.get("duration") else {}),
            }
        )
    return videos[:max_videos]


def _wait_for_channel_videos_grid(page: Page) -> None:
    """Wait until the channel videos grid renders."""
    selectors = (
        "a.ytLockupMetadataViewModelTitle, "
        "ytd-rich-item-renderer, "
        "ytd-rich-grid-media, "
        "a#video-title-link"
    )
    try:
        page.wait_for_selector(selectors, timeout=20000)
    except Exception:
        pass


def _collect_video_urls(page: Page, max_videos: int) -> list[dict[str, str]]:
    """Collect recent video URLs from the channel videos tab."""
    videos_tab = page.locator(
        "tp-yt-paper-tab:has-text('Videos'), "
        "yt-tab-shape:has-text('Videos'), "
        "a[href$='/videos']"
    ).first
    try:
        if videos_tab.is_visible(timeout=3000):
            videos_tab.click()
            page.wait_for_timeout(1500)
    except Exception:
        pass

    _wait_for_channel_videos_grid(page)

    for _ in range(5):
        page.evaluate("window.scrollBy(0, 900)")
        page.wait_for_timeout(700)

    videos = _collect_video_urls_via_script(page, max_videos)
    if videos:
        return videos

    video_links = page.locator(
        "a.ytLockupMetadataViewModelTitle, "
        "a.ytLockupViewModelContentImage, "
        "ytd-rich-grid-media a#video-title-link, "
        "ytd-grid-video-renderer a#video-title, "
        "a#video-title-link, "
        "a#video-title"
    )
    seen: set[str] = set()

    for index in range(min(video_links.count(), max(max_videos, 1) * 6)):
        if len(videos) >= max_videos:
            break
        link = video_links.nth(index)
        try:
            href = link.get_attribute("href") or ""
            if not _is_watch_video_href(href):
                continue
            full_url = (
                href if href.startswith("http") else f"https://www.youtube.com{href}"
            )
            video_id = full_url.split("v=")[-1].split("&")[0]
            if not video_id or video_id in seen:
                continue
            seen.add(video_id)
            title = link.inner_text().strip() or link.get_attribute("aria-label") or ""
            title = title.strip() or f"Video {video_id}"
            videos.append({"video_id": video_id, "title": title, "url": full_url})
        except Exception:
            continue

    return videos


def _parse_likes(text: str) -> int:
    """Parse like count from YouTube comment metadata text."""
    if not text:
        return 0
    cleaned = text.lower().replace(",", "").strip()
    match = re.search(r"(\d+(?:\.\d+)?)\s*([km])?", cleaned)
    if not match:
        return 0
    value = float(match.group(1))
    suffix = match.group(2) or ""
    if suffix == "k":
        return int(value * 1000)
    if suffix == "m":
        return int(value * 1_000_000)
    return int(value)


def _read_first_text(page: Page, selectors: str, timeout: int = 2000) -> str:
    """Return inner text from the first matching selector."""
    for selector in selectors.split(", "):
        locator = page.locator(selector.strip()).first
        try:
            if locator.count() > 0 and locator.is_visible(timeout=timeout):
                text = locator.inner_text().strip()
                if text:
                    return text
        except Exception:
            continue
    return ""


def _read_relative_publish_date(page: Page) -> str:
    """Read strings like '3 days ago' from the watch page metadata row."""
    try:
        value = page.evaluate(
            """
            () => {
              const spans = document.querySelectorAll(
                'yt-content-metadata-view-model span[role="text"], #info-strings yt-formatted-string'
              );
              for (const el of spans) {
                const text = (el.innerText || el.textContent || '').trim();
                if (/ago$/i.test(text)) return text;
              }
              return '';
            }
            """
        )
        return str(value or "").strip()
    except Exception:
        return ""


def _extract_video_metadata(page: Page, video: dict[str, str]) -> dict[str, Any]:
    """Extract comprehensive metadata from the current video page."""
    metadata: dict[str, Any] = dict(video)
    metadata = merge_metadata_fields(
        metadata, extract_player_metadata(page), overwrite=True
    )

    metadata["title"] = (
        _read_first_text(
            page,
            "h1.ytd-watch-metadata yt-formatted-string, h1 yt-formatted-string, "
            "#title h1 yt-formatted-string, #title yt-formatted-string, "
            "yt-formatted-string.ytd-watch-metadata-title",
        )
        or metadata.get("title")
        or video.get("title", "")
    )

    metadata["views"] = metadata.get("views") or _read_first_text(
        page,
        "yt-view-count-renderer span, yt-content-metadata-view-model span[role='text'], "
        "#info span.view-count, #info-container span.view-count, "
        "ytd-video-view-count-renderer span, #count .view-count",
    )

    metadata["published"] = metadata.get("published") or _read_first_text(
        page,
        "yt-content-metadata-view-model span[role='text'], "
        "#info-strings yt-formatted-string, #date yt-formatted-string, "
        "ytd-video-primary-info-renderer #info-strings yt-formatted-string, "
        "ytd-watch-info-text yt-formatted-string",
    )
    if metadata.get("published", "").lower().endswith("views"):
        metadata["published"] = _read_relative_publish_date(page) or video.get(
            "published", ""
        )

    metadata["duration"] = metadata.get("duration") or _read_first_text(
        page,
        "badge-shape.ytBadgeShapeThumbnailBadge .ytBadgeShapeText, "
        "ytd-thumbnail-overlay-time-status-renderer span, "
        ".ytp-time-duration, span.ytd-thumbnail-overlay-time-status-renderer",
    )

    like_button = page.locator(
        "like-button-view-model button, "
        "#top-level-buttons-computed like-button-view-model button, "
        "ytd-toggle-button-renderer #text"
    ).first
    try:
        if like_button.count() > 0:
            metadata["likes"] = (
                like_button.get_attribute("aria-label")
                or like_button.inner_text().strip()
            )
    except Exception:
        metadata["likes"] = ""

    dislike_button = page.locator(
        "dislike-button-view-model button, "
        "#top-level-buttons-computed dislike-button-view-model button"
    ).first
    try:
        if dislike_button.count() > 0:
            metadata["dislikes"] = (
                dislike_button.get_attribute("aria-label")
                or dislike_button.inner_text().strip()
            )
    except Exception:
        metadata["dislikes"] = ""

    metadata["category"] = _read_first_text(
        page,
        "ytd-watch-metadata #category ytd-badge-supported-renderer, "
        "#meta #category, ytd-badge-supported-renderer.style-scope",
    )

    metadata["hashtags"] = _read_first_text(
        page,
        "#description a[href*='hashtag'], #description-inline-expander a[href*='hashtag']",
    )

    metadata["game_title"] = _read_first_text(
        page,
        "ytd-rich-metadata-row-renderer #title, #above-the-fold #game-title",
    )

    metadata["chapters"] = _read_first_text(
        page,
        "ytd-macro-markers-list-item-renderer #title, #chapters-container",
        timeout=1500,
    )

    try:
        og_title = page.locator('meta[property="og:title"]').first
        if og_title.count() > 0:
            metadata["og_title"] = og_title.get_attribute("content") or ""
        og_desc = page.locator('meta[property="og:description"]').first
        if og_desc.count() > 0:
            metadata["og_description"] = og_desc.get_attribute("content") or ""
    except Exception:
        pass

    metadata["published"] = metadata.get("published") or _read_first_text(
        page,
        "yt-content-metadata-view-model span[role='text'], "
        "#info-strings yt-formatted-string, #date yt-formatted-string, "
        "ytd-video-primary-info-renderer #info-strings yt-formatted-string",
    )

    metadata["comment_count"] = _read_first_text(
        page,
        "#count .count-text, h2#count span, yt-formatted-string.count-text, "
        "ytd-comments-header-renderer #count, "
        "ytd-comments-header-renderer h2#count yt-formatted-string, "
        "yt-formatted-string.ytd-comments-header-renderer",
    )
    metadata["comment_count_value"] = _parse_comment_count(metadata["comment_count"])

    description = extract_full_description(page, _read_first_text)
    metadata["description"] = description
    metadata["video_about"] = build_video_about_summary(metadata)

    metadata["channel_on_video"] = _read_first_text(
        page,
        "ytd-channel-name a, #channel-name a, #owner #channel-name yt-formatted-string",
    )

    metadata["subscribers"] = _read_first_text(
        page,
        "#owner-sub-count, yt-formatted-string#subscriber-count, #subscriber-count",
    )

    try:
        thumb = page.locator('meta[property="og:image"]').first
        if thumb.count() > 0:
            metadata["thumbnail_url"] = thumb.get_attribute("content") or ""
    except Exception:
        metadata["thumbnail_url"] = ""

    if not metadata.get("thumbnail_url") and video.get("video_id"):
        metadata["thumbnail_url"] = (
            f"https://i.ytimg.com/vi/{video['video_id']}/hqdefault.jpg"
        )

    return metadata


def _comments_are_disabled(page: Page) -> bool:
    for text in COMMENT_DISABLED_TEXT:
        try:
            if page.locator(f"text={text}").first.is_visible(timeout=1000):
                return True
        except Exception:
            continue
    return False


def _scroll_to_comments_section(page: Page) -> None:
    """Scroll the watch page until the comments section is in view."""
    comments_header = page.locator(
        "ytd-comments#comments, ytd-comments-header-renderer, #comments #title"
    ).first
    for _ in range(12):
        try:
            if comments_header.count() > 0:
                comments_header.scroll_into_view_if_needed(timeout=3000)
                page.wait_for_timeout(800)
                if comments_header.is_visible(timeout=1500):
                    return
        except Exception:
            pass
        page.evaluate("window.scrollBy(0, 700)")
        page.wait_for_timeout(700)


def _expand_comments_if_collapsed(page: Page) -> None:
    for selector in (
        "tp-yt-paper-button:has-text('Show more')",
        "button:has-text('Show comments')",
        "#expand",
    ):
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=1000):
                button.click()
                page.wait_for_timeout(800)
        except Exception:
            continue


def _wait_for_comment_threads(page: Page, timeout_ms: int = 20000) -> bool:
    try:
        page.wait_for_selector(COMMENT_THREAD_SELECTOR, timeout=timeout_ms)
        return True
    except Exception:
        return False


def _scroll_to_load_more_comments(page: Page, target_count: int) -> int:
    """Scroll the comments panel until threads load or no new comments appear."""
    stale_rounds = 0
    last_count = 0
    max_rounds = max(12, (target_count // 2) + 8)

    for _ in range(max_rounds):
        threads = page.locator(COMMENT_THREAD_SELECTOR)
        current_count = threads.count()
        if current_count >= target_count:
            return current_count
        if current_count == last_count:
            stale_rounds += 1
        else:
            stale_rounds = 0
        if stale_rounds >= 8:
            break
        last_count = current_count
        page.evaluate(
            """
            () => {
              const comments = document.querySelector('ytd-comments#comments');
              if (comments) {
                comments.scrollTop = comments.scrollHeight;
              }
              const section = document.querySelector(
                'ytd-item-section-renderer#sections #contents'
              );
              if (section) {
                section.scrollTop = section.scrollHeight;
              }
              const renderer = document.querySelector('ytd-comments#comments #contents');
              if (renderer) {
                renderer.scrollTop = renderer.scrollHeight;
              }
              window.scrollBy(0, 1600);
            }
            """
        )
        page.wait_for_timeout(1600)

    return page.locator(COMMENT_THREAD_SELECTOR).count()


def _extract_comments_via_js(
    page: Page,
    video: dict[str, str],
    max_comments: int,
    channel_name: str = "",
) -> list[dict[str, Any]]:
    """Extract comments from the modern YouTube comment DOM via page.evaluate."""
    try:
        raw_comments = page.evaluate(_EXTRACT_COMMENTS_JS, max_comments)
    except Exception:
        return []

    comments: list[dict[str, Any]] = []
    for raw in raw_comments or []:
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_js_comment(raw, video, channel_name)
        if normalized.get("text"):
            comments.append(normalized)
    return comments


def _parse_comment_thread(
    thread,
    video: dict[str, str],
    index: int,
    channel_name: str = "",
) -> dict[str, Any] | None:
    """Extract one comment thread into a normalized dict (Playwright locator fallback)."""
    try:
        comment_root = thread.locator(
            "ytd-comment-view-model#comment, ytd-comment-view-model"
        ).first
        author = (
            comment_root.locator(
                "#author-text span, a#author-text, yt-formatted-string#author-text, "
                "#header-author a"
            )
            .first.inner_text()
            .strip()
        )
        text = (
            comment_root.locator("#content-text, yt-attributed-string#content-text")
            .first.inner_text()
            .strip()
        )
        if not text:
            return None

        timestamp = ""
        youtube_comment_id = ""
        try:
            time_link = comment_root.locator(
                "#published-time-text a, a.published-time-text"
            ).first
            timestamp = time_link.inner_text().strip()
            href = time_link.get_attribute("href") or ""
            match = re.search(r"[?&]lc=([^&]+)", href)
            if match:
                youtube_comment_id = match.group(1)
        except Exception:
            pass

        likes_text = ""
        like_locator = comment_root.locator(
            "#vote-count-middle, span#vote-count-middle, "
            "ytd-comment-engagement-bar #vote-count-middle"
        )
        if like_locator.count() > 0:
            likes_text = like_locator.first.inner_text().strip()

        is_pinned = (
            comment_root.locator(
                "#pinned-comment-badge, ytd-pinned-comment-badge-renderer"
            ).count()
            > 0
        )
        channel_replied = (
            thread.locator(
                "ytd-comment-replies-renderer ytd-author-comment-badge-renderer"
            ).count()
            > 0
        )

        comment_id = youtube_comment_id or f"{video['video_id']}_{index}"
        return {
            "author": author or "Unknown",
            "text": text,
            "likes": _parse_likes(likes_text),
            "timestamp": timestamp,
            "replied": False,
            "agent_replied": False,
            "channel_replied": channel_replied,
            "is_pinned": is_pinned,
            "is_channel_owner": is_channel_author_comment(
                {"author": author or "Unknown"}, channel_name
            ),
            "video_id": video["video_id"],
            "video_title": video["title"],
            "video_url": video["url"],
            "comment_id": comment_id,
            "youtube_comment_id": youtube_comment_id,
            "thread_index": index,
        }
    except Exception:
        return None


def _extract_comments_from_video(
    page: Page,
    video: dict[str, str],
    max_comments: int,
    channel_name: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Open a video page and extract metadata plus comment data."""
    page.goto(video["url"], wait_until="load", timeout=60000)
    page.wait_for_timeout(2500)
    _dismiss_optional_screens(page)

    video_metadata = _extract_video_metadata(page, video)
    reported_count = int(video_metadata.get("comment_count_value") or 0)

    if _comments_are_disabled(page):
        video_metadata["comments_disabled"] = True
        return [], video_metadata

    _scroll_to_comments_section(page)
    _expand_comments_if_collapsed(page)

    refreshed_count = _read_first_text(
        page,
        "#count .count-text, h2#count span, yt-formatted-string.count-text, "
        "ytd-comments-header-renderer #count, "
        "ytd-comments-header-renderer h2#count yt-formatted-string",
    )
    if refreshed_count:
        video_metadata["comment_count"] = refreshed_count
        video_metadata["comment_count_value"] = _parse_comment_count(refreshed_count)
        reported_count = int(video_metadata.get("comment_count_value") or 0)

    _wait_for_comment_threads(page)
    scrape_target = _resolve_scrape_target(reported_count, max_comments)
    loaded_threads = _scroll_to_load_more_comments(page, scrape_target)

    extract_limit = max_comments if max_comments > 0 else 0
    comments = _extract_comments_via_js(page, video, extract_limit, channel_name)

    comment_threads = page.locator(COMMENT_THREAD_SELECTOR)
    thread_count = comment_threads.count()
    if len(comments) < thread_count:
        fallback: list[dict[str, Any]] = []
        limit = extract_limit if extract_limit > 0 else thread_count
        for index in range(min(thread_count, limit or thread_count)):
            parsed = _parse_comment_thread(
                comment_threads.nth(index), video, index, channel_name
            )
            if parsed:
                fallback.append(parsed)
        if len(fallback) > len(comments):
            comments = fallback
    elif not comments:
        limit = extract_limit if extract_limit > 0 else thread_count
        for index in range(min(thread_count, limit or thread_count)):
            parsed = _parse_comment_thread(
                comment_threads.nth(index), video, index, channel_name
            )
            if parsed:
                comments.append(parsed)

    video_metadata["comments_loaded_threads"] = loaded_threads
    video_metadata["comments_scraped_count"] = len(comments)
    video_metadata["comments_scrape_target"] = scrape_target
    if reported_count and len(comments) < reported_count:
        video_metadata["comments_scrape_warning"] = (
            f"YouTube shows {reported_count} comments on this video, but only "
            f"{len(comments)} comment threads were scraped. "
            "Try BROWSER_HEADLESS=false, set MAX_COMMENTS_PER_VIDEO=0, or check "
            "whether comments require sign-in."
        )

    return comments, video_metadata


def _get_latest_video(page: Page, channel_url: str = "") -> dict[str, str] | None:
    """Return the most recent standard video from the channel videos tab."""
    if channel_url:
        page.goto(_channel_videos_url(channel_url), wait_until="load", timeout=60000)
        page.wait_for_timeout(2500)
        _dismiss_optional_screens(page)
    videos = _collect_video_urls(page, max_videos=1)
    return videos[0] if videos else None


def fetch_channel_data(
    channel_url: str = "",
    channel_name: str = "",
) -> dict[str, Any]:
    """Login, open the target channel, and collect comments from its latest video."""
    config = get_youtube_config()
    channel_url, channel_name = resolve_target_channel(channel_url, channel_name)

    if not channel_url and not channel_name:
        return {
            "success": False,
            "error": (
                "No target channel specified. Set YOUTUBE_CHANNEL_NAME or "
                "YOUTUBE_CHANNEL_URL in .env, or pass channel_name/channel_url."
            ),
            "comments": [],
        }

    playwright = browser = context = page = None
    keep_session = False
    stored_video_url = ""

    try:
        playwright, browser, context, page, logged_in = ensure_youtube_session()
        if not logged_in:
            return {
                "success": False,
                "error": "YouTube login failed. Check YOUTUBE_EMAIL and YOUTUBE_PASSWORD.",
                "comments": [],
            }

        resolved_url = navigate_to_channel(page, channel_url, channel_name)
        if "/@" in resolved_url and "/videos" not in resolved_url:
            resolved_url = _channel_videos_url(resolved_url)
        resolved_name = channel_name or _extract_channel_name(page)
        channel_id = _extract_channel_id(resolved_url)

        latest_video = _get_latest_video(page, resolved_url)
        if not latest_video:
            return {
                "success": False,
                "error": f"No videos found on channel '{resolved_name}'.",
                "comments": [],
            }

        all_comments, video_metadata = _extract_comments_from_video(
            page,
            latest_video,
            config["max_comments_per_video"],
            resolved_name,
        )
        latest_video_enriched = merge_video_records(latest_video, video_metadata)

        save_session(context)

        result: dict[str, Any] = {
            "success": True,
            "youtube_channel_name": resolved_name,
            "youtube_channel_url": resolved_url,
            "youtube_channel_id": channel_id,
            "latest_video": latest_video_enriched,
            "video_metadata": video_metadata,
            "comments": all_comments,
            "videos_scanned": 1,
            "comments_reported_count": video_metadata.get("comment_count_value", 0),
            "comments_scraped_count": len(all_comments),
        }
        warning = video_metadata.get("comments_scrape_warning")
        if warning:
            result["warning"] = warning
        if video_metadata.get("comments_disabled"):
            result["warning"] = "Comments are turned off on this video."
        stored_video_url = str(latest_video_enriched.get("url") or "")
        keep_session = True
        return result
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "comments": [],
        }
    finally:
        if keep_session and config.get("keep_browser_open", True) and page is not None:
            _store_browser_session(
                playwright, browser, context, page, video_url=stored_video_url
            )
        else:
            close_browser_session(playwright, browser, context)


def _is_page_alive(page: Page | None) -> bool:
    if page is None:
        return False
    try:
        _ = page.url
        return True
    except Exception:
        return False


def _ensure_page_on_video(page: Page, video_url: str) -> None:
    """Navigate the current tab to the watch page and scroll comments into view."""
    target = (video_url or "").strip()
    if target:
        page.goto(target, wait_until="load", timeout=60000)
        page.wait_for_timeout(2500)
        _dismiss_optional_screens(page)
    _scroll_to_comments_section(page)
    page.wait_for_timeout(600)


def _wait_for_enabled_yt_button(page: Page, scope, aria_label: str, timeout_ms: int = 12000):
    """Wait until a yt-button-shape CTA button is visible and enabled."""
    selector = (
        f'yt-button-shape button[aria-label="{aria_label}"].ytSpecButtonShapeNextCallToAction, '
        f'yt-button-shape button[aria-label="{aria_label}"].ytSpecButtonShapeNextFilled, '
        f'button.ytSpecButtonShapeNextCallToAction[aria-label="{aria_label}"]'
    )
    button = scope.locator(selector).first
    button.wait_for(state="visible", timeout=timeout_ms)
    deadline = timeout_ms
    while deadline > 0:
        disabled = button.get_attribute("aria-disabled")
        if disabled in (None, "false"):
            return button
        page.wait_for_timeout(200)
        deadline -= 200
    return button


def _open_main_comment_composer(page: Page) -> None:
    """Click the simplebox placeholder so the main comment field opens."""
    for selector in (
        "yt-formatted-string#simplebox-placeholder",
        "#simplebox-placeholder",
        "ytd-comment-simplebox-renderer #placeholder-area",
        "ytd-comment-simplebox-renderer",
    ):
        locator = page.locator(selector).first
        try:
            if locator.count() > 0 and locator.is_visible(timeout=3000):
                locator.scroll_into_view_if_needed(timeout=3000)
                locator.click()
                page.wait_for_timeout(900)
                return
        except Exception:
            continue
    raise RuntimeError("Could not open the main comment composer")


def _click_yt_submit_button(page: Page, scope, aria_label: str) -> bool:
    """Click a filled CTA yt-button-shape submit button (Comment or Reply)."""
    try:
        submit = _wait_for_enabled_yt_button(page, scope, aria_label)
        submit.scroll_into_view_if_needed(timeout=3000)
        submit.click()
        page.wait_for_timeout(2000)
        return True
    except Exception:
        return False


def _find_comment_thread(page: Page, comment: dict[str, Any]):
    """Locate a comment thread on the current watch page."""
    youtube_comment_id = str(comment.get("youtube_comment_id") or "").strip()
    if youtube_comment_id:
        thread = page.locator(
            f'ytd-comment-thread-renderer:has(a[href*="lc={youtube_comment_id}"])'
        ).first
        try:
            if thread.count() > 0:
                return thread
        except Exception:
            pass

    thread_index = comment.get("thread_index")
    if thread_index is not None:
        return page.locator(COMMENT_THREAD_SELECTOR).nth(int(thread_index))

    comment_id = str(comment.get("comment_id") or "")
    if "_" in comment_id:
        try:
            index = int(comment_id.rsplit("_", 1)[-1])
            return page.locator(COMMENT_THREAD_SELECTOR).nth(index)
        except ValueError:
            pass
    return None


def _video_url_for_comment(video_url: str, comment: dict[str, Any]) -> str:
    """Build a watch URL that scrolls YouTube to the target comment when possible."""
    base_url = (video_url or "").split("&lc=")[0].split("?lc=")[0].strip()
    if not base_url:
        return video_url
    youtube_comment_id = str(comment.get("youtube_comment_id") or "").strip()
    if not youtube_comment_id:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}lc={youtube_comment_id}"


def _prepare_video_for_reply(
    page: Page, video_url: str, comment: dict[str, Any]
) -> None:
    """Open the watch page and ensure the comments panel is ready."""
    target_url = _video_url_for_comment(video_url, comment)
    page.goto(target_url, wait_until="load", timeout=60000)
    page.wait_for_timeout(2500)
    _dismiss_optional_screens(page)
    _scroll_to_comments_section(page)
    _wait_for_comment_threads(page, timeout_ms=15000)


def _open_thread_reply_box(page: Page, thread) -> bool:
    """Click the inline Reply button on a comment thread."""
    thread.scroll_into_view_if_needed(timeout=5000)
    page.wait_for_timeout(400)
    for selector in (
        '#reply-button-end yt-button-shape button[aria-label="Reply"].ytSpecButtonShapeNextText',
        '#reply-button-end yt-button-shape button[aria-label="Reply"]:not(.ytSpecButtonShapeNextCallToAction)',
        THREAD_REPLY_BUTTON_SELECTOR,
    ):
        reply_button = thread.locator(selector).first
        try:
            if reply_button.is_visible(timeout=3000):
                reply_button.click()
                page.wait_for_timeout(900)
                return True
        except Exception:
            continue
    return False


def _type_in_contenteditable(page: Page, input_box, text: str) -> None:
    """Type into YouTube's contenteditable comment/reply field."""
    input_box.click()
    page.wait_for_timeout(300)
    # YouTube only enables the Comment button after real keyboard input events.
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(text, delay=12)
    page.wait_for_timeout(400)
    try:
        handle = input_box.element_handle(timeout=2000)
        if handle:
            typed = page.evaluate("(el) => (el.innerText || el.textContent || '').trim()", handle)
            if not typed:
                page.evaluate(
                    """(el, value) => {
                      el.focus();
                      el.textContent = value;
                      el.dispatchEvent(new InputEvent('input', { bubbles: true }));
                    }""",
                    handle,
                    text,
                )
    except Exception:
        pass


def _type_in_reply_box(page: Page, reply_box, reply_text: str) -> None:
    """Type into YouTube's contenteditable reply field."""
    _type_in_contenteditable(page, reply_box, reply_text)


def _submit_thread_reply(page: Page, thread) -> bool:
    """Click the filled CTA Reply button in the opened comment box."""
    commentbox = thread.locator("ytd-commentbox").last
    try:
        commentbox.wait_for(state="visible", timeout=8000)
    except Exception:
        commentbox = page.locator("ytd-commentbox").last
    return _click_yt_submit_button(page, commentbox, "Reply")


def post_comment_reply(
    page: Page, comment: dict[str, Any], reply_text: str
) -> tuple[bool, str]:
    """Post a reply to a comment on the current video page."""
    if not reply_text.strip():
        return False, "Reply text is empty"
    if _is_blocked_post_text(reply_text):
        return False, "Reply text looks like test/diagnostic content and was blocked"

    try:
        thread = _find_comment_thread(page, comment)
        if thread is None:
            return False, "Could not locate comment thread on page"

        if not _open_thread_reply_box(page, thread):
            return False, "Could not open inline Reply button"

        reply_box = thread.locator(
            '#contenteditable-root[aria-label="Add a reply..."]'
        ).first
        reply_box.wait_for(state="visible", timeout=10000)
        _type_in_reply_box(page, reply_box, reply_text)
        page.wait_for_timeout(700)

        if _submit_thread_reply(page, thread):
            return True, ""
        return False, "Reply button stayed disabled or was not clickable"
    except Exception as exc:
        return False, str(exc)


def post_video_comment(page: Page, comment_text: str) -> tuple[bool, str]:
    """Post a new top-level comment on the current video watch page."""
    if not comment_text.strip():
        return False, "Comment text is empty"
    if _is_blocked_post_text(comment_text):
        return False, "Comment text looks like test/diagnostic content and was blocked"

    snippet = comment_text.strip()[:48]
    try:
        _open_main_comment_composer(page)

        comment_box = page.locator(
            '#contenteditable-root[aria-label="Add a comment..."]'
        ).first
        comment_box.wait_for(state="visible", timeout=10000)
        _type_in_contenteditable(page, comment_box, comment_text)
        page.wait_for_timeout(700)

        simplebox = page.locator("ytd-comment-simplebox-renderer").first
        if not _click_yt_submit_button(page, simplebox, "Comment"):
            header = page.locator("ytd-comments-header-renderer").first
            if not _click_yt_submit_button(page, header, "Comment"):
                return False, "Comment button stayed disabled or was not clickable"

        page.wait_for_timeout(2500)
        if page.locator(f"text={snippet}").count() > 0:
            return True, ""
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _post_on_page(
    page: Page,
    video_url: str,
    *,
    replies: list[dict[str, Any]] | None = None,
    new_comments: list[dict[str, Any]] | None = None,
    post_replies_enabled: bool | None = None,
    post_new_comments_enabled: bool | None = None,
) -> dict[str, Any]:
    """Post replies and/or new comments on the current or given video page."""
    replies = list(replies or [])
    new_comments = list(new_comments or [])
    config = get_youtube_config()
    replies_enabled = (
        post_replies_enabled
        if post_replies_enabled is not None
        else config["enable_comment_replies"]
    )
    new_comments_enabled = (
        post_new_comments_enabled
        if post_new_comments_enabled is not None
        else config["enable_new_comments"]
    )

    if video_url:
        try:
            _ensure_page_on_video(page, video_url)
        except Exception as exc:
            msg = str(exc)
            return {
                "posted": 0,
                "failed": len(replies) + len(new_comments),
                "error": msg,
                "replies": replies,
                "new_comments": new_comments,
            }
    elif not _is_page_alive(page):
        return {
            "posted": 0,
            "failed": len(replies) + len(new_comments),
            "error": "Browser page is no longer available",
            "replies": replies,
            "new_comments": new_comments,
        }

    reply_posted = reply_failed = 0
    for reply in replies:
        if not replies_enabled:
            break
        target_url = str(reply.get("video_url") or video_url or "")
        if target_url:
            deep_link = _video_url_for_comment(target_url, reply)
            _ensure_page_on_video(page, deep_link)
            page.wait_for_timeout(1500)
            _wait_for_comment_threads(page, timeout_ms=12000)
        success, error = post_comment_reply(page, reply, reply.get("reply_text", ""))
        if success:
            reply_posted += 1
            reply["posted"] = True
            reply["post_error"] = ""
        else:
            reply_failed += 1
            reply["posted"] = False
            reply["post_error"] = error or "Failed to post reply"

    new_posted = new_failed = 0
    for item in new_comments[: config["max_new_comments"]]:
        if not new_comments_enabled:
            break
        success, error = post_video_comment(page, item.get("comment_text", ""))
        if success:
            new_posted += 1
            item["posted"] = True
            item["post_error"] = ""
        else:
            new_failed += 1
            item["posted"] = False
            item["post_error"] = error or "Failed to post new comment"

    context = _BROWSER_SESSION.get("context")
    if context is not None:
        save_session(context)

    return {
        "posted": reply_posted,
        "failed": reply_failed,
        "replies": replies,
        "failed_replies": [r for r in replies if not r.get("posted")],
        "new_posted": new_posted,
        "new_failed": new_failed,
        "new_comments": new_comments,
    }


def post_new_video_comments(
    comments: list[dict[str, Any]],
    *,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Post generated top-level comments, reusing the open browser when available."""
    config = get_youtube_config()
    post_enabled = enabled if enabled is not None else config["enable_new_comments"]
    if not post_enabled:
        return {
            "posted": 0,
            "skipped": len(comments),
            "failed": 0,
            "message": "New comments disabled",
            "new_comments": comments,
        }

    video_url = str(comments[0].get("video_url") or "") if comments else ""
    try:
        page, error = prepare_browser_for_posting(video_url)
        if error or page is None:
            msg = error or "Browser not available"
            for item in comments:
                item["posted"] = False
                item["post_error"] = msg
            return {
                "posted": 0,
                "failed": len(comments),
                "error": msg,
                "new_comments": comments,
            }

        result = _post_on_page(
            page,
            video_url,
            new_comments=comments,
            post_new_comments_enabled=True,
        )
        return {
            "posted": result.get("new_posted", 0),
            "failed": result.get("new_failed", 0),
            "new_comments": result.get("new_comments", comments),
            "error": result.get("error"),
        }
    except Exception as exc:
        msg = str(exc)
        for item in comments:
            item["posted"] = False
            item["post_error"] = msg
        return {
            "posted": 0,
            "failed": len(comments),
            "error": msg,
            "new_comments": comments,
        }


def post_replies_to_comments(
    replies: list[dict[str, Any]],
    *,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Post generated replies, reusing the open browser session from scrape when available."""
    config = get_youtube_config()
    post_enabled = enabled if enabled is not None else config["enable_comment_replies"]
    if not post_enabled:
        return {
            "posted": 0,
            "skipped": len(replies),
            "message": "Replies disabled",
        }

    video_url = str(replies[0].get("video_url") or "") if replies else ""
    try:
        page, error = prepare_browser_for_posting(video_url)
        if error or page is None:
            msg = error or "Browser not available"
            for reply in replies:
                reply["posted"] = False
                reply["post_error"] = msg
            return {
                "posted": 0,
                "failed": len(replies),
                "error": msg,
                "replies": replies,
                "failed_replies": list(replies),
            }

        result = _post_on_page(
            page,
            video_url,
            replies=replies,
            post_replies_enabled=True,
        )
        return {
            "posted": result.get("posted", 0),
            "failed": result.get("failed", 0),
            "replies": result.get("replies", replies),
            "failed_replies": result.get("failed_replies", []),
            "error": result.get("error"),
        }
    except Exception as exc:
        msg = str(exc)
        for reply in replies:
            reply["posted"] = False
            reply["post_error"] = msg
        return {
            "posted": 0,
            "failed": len(replies),
            "error": msg,
            "replies": replies,
            "failed_replies": list(replies),
        }


__all__ = [
    "fetch_channel_data",
    "post_replies_to_comments",
    "post_comment_reply",
    "post_video_comment",
    "post_new_video_comments",
    "prepare_browser_for_posting",
    "release_browser_session",
]
