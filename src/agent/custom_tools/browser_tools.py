"""Playwright browser automation for YouTube login and navigation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    sync_playwright,
)

from agent.config import get_youtube_config

_DEFAULT_PLAYWRIGHT_BROWSERS = Path.home() / ".cache" / "ms-playwright"
if not os.getenv("PLAYWRIGHT_BROWSERS_PATH") and _DEFAULT_PLAYWRIGHT_BROWSERS.exists():
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT_PLAYWRIGHT_BROWSERS)

YOUTUBE_HOME_URL = "https://www.youtube.com"
GOOGLE_SIGNIN_URL = (
    "https://accounts.google.com/v3/signin/identifier"
    "?continue=https://www.youtube.com/"
    "&flowName=GlifWebSignIn"
    "&flowEntry=ServiceLogin"
)

EMAIL_SELECTORS = (
    "#identifierId",
    'input[name="identifier"]',
    'input[type="email"]',
    'input[autocomplete="username"]',
)

PASSWORD_SELECTORS = (
    'input[name="Passwd"]',
    'input[type="password"]',
    'input[autocomplete="current-password"]',
)

NEXT_BUTTON_SELECTORS = (
    "#identifierNext button",
    "#identifierNext",
    'button:has-text("Next")',
)

PASSWORD_NEXT_SELECTORS = (
    "#passwordNext button",
    "#passwordNext",
    'button:has-text("Next")',
)

SIGN_IN_SELECTORS = (
    'a[aria-label="Sign in"]',
    'ytd-button-renderer a[href*="accounts.google"]',
    'a[href*="ServiceLogin"]',
    'tp-yt-paper-button:has-text("Sign in")',
    'yt-button-shape a:has-text("Sign in")',
)

LOGGED_IN_SELECTORS = (
    "#avatar-btn",
    "button#avatar-btn",
    'button[aria-label*="Google Account"]',
    'img[alt*="Avatar"]',
)


def _login_timeout_ms() -> int:
    raw = os.getenv("BROWSER_LOGIN_TIMEOUT_MS", "45000").strip()
    try:
        return max(15000, int(raw))
    except ValueError:
        return 45000


def _new_browser_context(
    browser: Browser,
    session_path: str | None = None,
) -> BrowserContext:
    """Create a browser context, optionally loading a saved session."""
    kwargs: dict = {
        "viewport": {"width": 1280, "height": 900},
        "locale": "en-US",
        "user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
    }
    if session_path and Path(session_path).exists():
        kwargs["storage_state"] = session_path
    return browser.new_context(**kwargs)


def launch_browser(
    headless: bool | None = None,
) -> tuple[Playwright, Browser, BrowserContext, Page]:
    """Launch Chromium with Playwright and return playwright, browser, context, page."""
    config = get_youtube_config()
    headless = config["headless"] if headless is None else headless

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context = _new_browser_context(browser)
    page = context.new_page()
    return playwright, browser, context, page


def save_session(context: BrowserContext, path: str | None = None) -> str:
    """Persist browser storage state for session reuse."""
    config = get_youtube_config()
    session_path = path or config["session_path"]
    Path(session_path).parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=session_path)
    return session_path


def load_session(
    browser: Browser,
    path: str | None = None,
) -> BrowserContext:
    """Load a previously saved browser session."""
    config = get_youtube_config()
    session_path = path or config["session_path"]
    return _new_browser_context(browser, session_path)


def _first_visible_locator(
    page: Page,
    selectors: Iterable[str],
    timeout_ms: int,
) -> Locator:
    """Return the first locator that becomes visible within the timeout."""
    selector_list = tuple(selectors)
    per_selector_timeout = max(3000, timeout_ms // max(len(selector_list), 1))
    last_error: Exception | None = None

    for selector in selector_list:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=per_selector_timeout)
            return locator
        except Exception as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise last_error
    raise TimeoutError("No matching element became visible.")


def _click_if_visible(
    page: Page, selectors: Iterable[str], timeout_ms: int = 2000
) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=timeout_ms):
                locator.click()
                return True
        except Exception:
            continue
    return False


def _is_logged_in(page: Page) -> bool:
    for selector in LOGGED_IN_SELECTORS:
        if page.locator(selector).count() > 0:
            try:
                if page.locator(selector).first.is_visible(timeout=1000):
                    return True
            except Exception:
                continue
    return False


def _dismiss_optional_screens(page: Page) -> None:
    """Skip optional Google/YouTube setup prompts when they appear."""
    optional_selectors = [
        "button:has-text('Not now')",
        "button:has-text('Skip')",
        "button:has-text('No thanks')",
        "button:has-text('Dismiss')",
        "button:has-text('I agree')",
        "#confirm",
    ]
    for selector in optional_selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=1500):
                locator.click()
                page.wait_for_timeout(500)
        except Exception:
            continue


def _open_google_sign_in(page: Page, timeout_ms: int) -> None:
    """Open Google sign-in from YouTube, falling back to the accounts URL."""
    page.goto(YOUTUBE_HOME_URL, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(2000)
    _dismiss_optional_screens(page)

    if _is_logged_in(page):
        return

    if _click_if_visible(page, SIGN_IN_SELECTORS, timeout_ms=3000):
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(1500)
        return

    page.goto(GOOGLE_SIGNIN_URL, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(1500)


def _prepare_identifier_step(page: Page) -> None:
    """Handle account chooser screens before entering email."""
    for selector in EMAIL_SELECTORS:
        try:
            if page.locator(selector).first.is_visible(timeout=1000):
                return
        except Exception:
            continue

    _click_if_visible(
        page,
        (
            "text=Use another account",
            "div:has-text('Use another account')",
            "text=Add account",
        ),
        timeout_ms=2000,
    )


def _fill_google_identifier(page: Page, email: str, timeout_ms: int) -> None:
    _prepare_identifier_step(page)
    email_input = _first_visible_locator(page, EMAIL_SELECTORS, timeout_ms)
    email_input.click()
    email_input.fill(email)
    if not _click_if_visible(page, NEXT_BUTTON_SELECTORS, timeout_ms=5000):
        page.keyboard.press("Enter")
    page.wait_for_timeout(1500)


def _fill_google_password(page: Page, password: str, timeout_ms: int) -> None:
    password_input = _first_visible_locator(page, PASSWORD_SELECTORS, timeout_ms)
    password_input.click()
    password_input.fill(password)
    if not _click_if_visible(page, PASSWORD_NEXT_SELECTORS, timeout_ms=5000):
        page.keyboard.press("Enter")
    page.wait_for_timeout(2500)
    _dismiss_optional_screens(page)


def login_youtube(page: Page, email: str = "", password: str = "") -> bool:
    """Log in to YouTube via Google account credentials."""
    config = get_youtube_config()
    email = email or config["email"]
    password = password or config["password"]
    timeout_ms = _login_timeout_ms()

    if not email or not password:
        raise ValueError(
            "YOUTUBE_EMAIL and YOUTUBE_PASSWORD must be set in .env for login."
        )

    try:
        _open_google_sign_in(page, timeout_ms)
        if _is_logged_in(page):
            return True

        _fill_google_identifier(page, email, timeout_ms)
        _fill_google_password(page, password, timeout_ms)
        _dismiss_optional_screens(page)

        if "myaccount.google.com" in page.url or "youtube.com" not in page.url:
            page.goto(
                YOUTUBE_HOME_URL, wait_until="domcontentloaded", timeout=timeout_ms
            )
            page.wait_for_timeout(2000)
            _dismiss_optional_screens(page)

        return _is_logged_in(page)
    except Exception as exc:
        headless_hint = ""
        if config["headless"]:
            headless_hint = (
                " Try setting BROWSER_HEADLESS=false in .env so you can complete "
                "any Google security prompts manually."
            )
        raise TimeoutError(
            f"YouTube login failed while waiting for Google sign-in fields: {exc}.{headless_hint}"
        ) from exc


def navigate_to_channel(
    page: Page, channel_url: str = "", channel_name: str = ""
) -> str:
    """Navigate to a YouTube channel by URL or name. Returns resolved channel URL."""
    if channel_url:
        url = channel_url.strip()
        if not url.startswith("http"):
            url = f"https://www.youtube.com/{url.lstrip('/')}"
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        return page.url

    if channel_name:
        search_url = f"https://www.youtube.com/results?search_query={channel_name.replace(' ', '+')}"
        page.goto(search_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        channel_link = page.locator(
            "ytd-channel-renderer a#main-link, "
            "a[href*='/@'], a[href*='/channel/'], a[href*='/c/']"
        ).first
        channel_link.wait_for(state="visible", timeout=10000)
        channel_link.click()
        page.wait_for_timeout(2000)
        return page.url

    raise ValueError("Provide channel_url or channel_name to navigate.")


def ensure_youtube_session(
    headless: bool | None = None,
) -> tuple[Playwright, Browser, BrowserContext, Page, bool]:
    """Launch browser, reuse or create session, return session components."""
    config = get_youtube_config()
    headless = config["headless"] if headless is None else headless
    session_path = config["session_path"]

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context = _new_browser_context(
        browser,
        session_path if Path(session_path).exists() else None,
    )
    page = context.new_page()
    logged_in = False

    page.goto(
        YOUTUBE_HOME_URL, wait_until="domcontentloaded", timeout=_login_timeout_ms()
    )
    page.wait_for_timeout(1500)
    logged_in = _is_logged_in(page)

    if not logged_in:
        logged_in = login_youtube(page)
        if logged_in:
            save_session(context, session_path)

    return playwright, browser, context, page, logged_in


def close_browser_session(
    playwright: Playwright | None,
    browser: Browser | None,
    context: BrowserContext | None,
) -> None:
    """Clean up Playwright resources."""
    for resource in (context, browser):
        if resource is not None:
            try:
                resource.close()
            except Exception:
                pass
    if playwright is not None:
        try:
            playwright.stop()
        except Exception:
            pass


__all__ = [
    "launch_browser",
    "login_youtube",
    "save_session",
    "load_session",
    "navigate_to_channel",
    "ensure_youtube_session",
    "close_browser_session",
]
