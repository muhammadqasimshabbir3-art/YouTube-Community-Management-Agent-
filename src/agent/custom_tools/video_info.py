"""Latest-video description and summary helpers."""

from __future__ import annotations

import os
import re
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from playwright.sync_api import Page


def extract_description_from_player_response(page: Page) -> str:
    """Read the full video description from YouTube's embedded player data."""
    try:
        description = page.evaluate(
            """
            () => {
              const response = window.ytInitialPlayerResponse;
              if (!response || !response.videoDetails) return '';
              return response.videoDetails.shortDescription
                || response.videoDetails.description
                || '';
            }
            """
        )
        return str(description or "").strip()
    except Exception:
        return ""


def expand_video_description(page: Page) -> None:
    """Expand the collapsed description block on a watch page."""
    selectors = (
        "tp-yt-paper-button#expand",
        "#expand",
        "ytd-text-inline-expander #expand",
        "#description-inline-expander #expand",
        "button:has-text('...more')",
        "button:has-text('Show more')",
    )
    for selector in selectors:
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=1000):
                button.click()
                page.wait_for_timeout(600)
        except Exception:
            continue


def extract_full_description(
    page: Page,
    read_text: Callable[[Page, str, int], str],
) -> str:
    """Collect the fullest description available from DOM, meta tags, and player JSON."""
    expand_video_description(page)

    description = read_text(
        page,
        "ytd-text-inline-expander #expanded yt-attributed-string, "
        "ytd-text-inline-expander #expanded, "
        "#description-inline-expander yt-attributed-string, "
        "#description yt-attributed-string, "
        "#description-inline-expander, "
        "#description",
        3000,
    )
    if not description:
        description = extract_description_from_player_response(page)
    if not description:
        try:
            og_desc = page.locator('meta[property="og:description"]').first
            if og_desc.count() > 0:
                description = (og_desc.get_attribute("content") or "").strip()
        except Exception:
            pass
    if not description:
        try:
            description = page.evaluate(
                """
                () => {
                  const el = document.querySelector(
                    'ytd-watch-metadata #description, #description-inline-expander'
                  );
                  return el ? el.innerText : '';
                }
                """
            )
            description = str(description or "").strip()
        except Exception:
            pass
    return description


def _heuristic_video_about(metadata: dict[str, Any]) -> str:
    title = (metadata.get("title") or "Latest video").strip()
    description = (
        metadata.get("description") or metadata.get("og_description") or ""
    ).strip()
    category = (metadata.get("category") or "").strip()
    game_title = (metadata.get("game_title") or "").strip()

    if not description:
        parts = [f"The latest video on this channel is titled '{title}'."]
        if category:
            parts.append(f"Category: {category}.")
        if game_title:
            parts.append(f"Topic/game: {game_title}.")
        parts.append("YouTube did not expose a description for this video.")
        return " ".join(parts)

    excerpt = re.sub(r"\s+", " ", description)
    if len(excerpt) > 400:
        excerpt = excerpt[:400].rsplit(" ", 1)[0] + "..."

    topic_bits = []
    if category:
        topic_bits.append(f"category {category}")
    if game_title:
        topic_bits.append(f"topic {game_title}")
    topic_suffix = f" It is listed under {', '.join(topic_bits)}." if topic_bits else ""
    return f"This latest video ('{title}') is about: {excerpt}{topic_suffix}"


def build_video_about_summary(metadata: dict[str, Any]) -> str:
    """Explain what the latest video is about in plain language."""
    api_key = os.getenv("GROQ_API_KEY")
    title = metadata.get("title") or "Latest video"
    description = metadata.get("description") or metadata.get("og_description") or ""

    if not api_key:
        return _heuristic_video_about(metadata)

    prompt = (
        "Summarize what this YouTube video is about in 2-4 clear sentences for a "
        "community manager. Focus on topic, purpose, and audience takeaways.\n\n"
        f"Title: {title}\n"
        f"Views: {metadata.get('views', 'N/A')}\n"
        f"Published: {metadata.get('published', 'N/A')}\n"
        f"Category: {metadata.get('category', 'N/A')}\n"
        f"Game/Topic: {metadata.get('game_title', 'N/A')}\n"
        f"Description:\n{description[:2500]}"
    )
    try:
        model = ChatGroq(model="llama-3.1-8b-instant", temperature=0.2, api_key=api_key)
        response = model.invoke(
            [
                SystemMessage(
                    content="You summarize YouTube videos clearly and concisely."
                ),
                HumanMessage(content=prompt),
            ]
        )
        summary = str(response.content).strip()
        if summary:
            return summary
    except Exception:
        pass
    return _heuristic_video_about(metadata)


def extract_player_metadata(page: Page) -> dict[str, Any]:
    """Read reliable video metadata from YouTube's embedded player JSON."""
    try:
        raw = page.evaluate(
            """
            () => {
              const response = window.ytInitialPlayerResponse;
              if (!response) return {};
              const details = response.videoDetails || {};
              const micro = response.microformat?.playerMicroformatRenderer || {};
              const thumbs = details.thumbnail?.thumbnails || [];
              return {
                video_id: details.videoId || '',
                title: details.title || '',
                description: details.shortDescription || details.description || '',
                views_raw: details.viewCount || '',
                length_seconds: details.lengthSeconds || '',
                channel: details.author || '',
                published_raw: micro.publishDate || micro.uploadDate || '',
                thumbnail_url: thumbs.length ? thumbs[thumbs.length - 1].url : '',
              };
            }
            """
        )
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    metadata: dict[str, Any] = {}
    if raw.get("video_id"):
        metadata["video_id"] = raw["video_id"]
    if raw.get("title"):
        metadata["title"] = str(raw["title"]).strip()
    if raw.get("description"):
        metadata["description"] = str(raw["description"]).strip()
    if raw.get("channel"):
        metadata["channel_on_video"] = str(raw["channel"]).strip()
    if raw.get("thumbnail_url"):
        metadata["thumbnail_url"] = str(raw["thumbnail_url"]).strip()

    views_raw = raw.get("views_raw")
    if views_raw not in (None, ""):
        metadata["views"] = format_view_count(views_raw)

    published_raw = raw.get("published_raw")
    if published_raw:
        metadata["published"] = format_publish_date(str(published_raw))

    length_seconds = raw.get("length_seconds")
    if length_seconds not in (None, ""):
        metadata["duration"] = format_duration_seconds(length_seconds)

    return metadata


def format_view_count(raw: str | int) -> str:
    """Format YouTube view counts for display."""
    try:
        count = int(str(raw).replace(",", "").strip())
    except ValueError:
        return str(raw)
    if count >= 1_000_000:
        value = count / 1_000_000
        return f"{value:.1f}M views".replace(".0M", "M")
    if count >= 1_000:
        value = count / 1_000
        return f"{value:.1f}K views".replace(".0K", "K")
    return f"{count} views"


def format_duration_seconds(raw: str | int) -> str:
    """Format seconds into H:MM:SS or M:SS."""
    try:
        total = int(str(raw))
    except ValueError:
        return str(raw)
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def format_publish_date(raw: str) -> str:
    """Normalize publish timestamps from YouTube microformat data."""
    value = raw.strip()
    if not value:
        return ""
    if "ago" in value.lower():
        return value
    if "T" in value:
        return value.split("T", 1)[0]
    return value


def merge_metadata_fields(
    target: dict[str, Any],
    source: dict[str, Any],
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Merge metadata dictionaries, keeping existing values unless overwrite is True."""
    merged = dict(target)
    for key, value in source.items():
        if value in (None, "", [], {}):
            continue
        if overwrite or not merged.get(key):
            merged[key] = value
    return merged


def merge_video_records(
    base: dict[str, Any], metadata: dict[str, Any]
) -> dict[str, Any]:
    """Merge scrape metadata into the latest-video record without blank overwrites."""
    merged = dict(base)
    for key, value in metadata.items():
        if value in (None, "", [], {}):
            continue
        merged[key] = value
    return merged
