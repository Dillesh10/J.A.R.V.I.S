import os
import urllib.parse
import webbrowser
import threading
from dotenv import load_dotenv

# ─── Persistent browser state (runs in background across calls) ─────────────
_browser = None
_page = None
_playwright = None
_lock = threading.Lock()


def _ensure_browser():
    """Lazily starts a persistent Playwright Chromium browser session."""
    global _browser, _page, _playwright
    with _lock:
        if _browser is None:
            from playwright.sync_api import sync_playwright
            _playwright = sync_playwright().start()
            _browser = _playwright.chromium.launch(headless=False, slow_mo=100)
            _page = _browser.new_page()
            _page.set_viewport_size({"width": 1280, "height": 800})
    return _page


# ─── YouTube ─────────────────────────────────────────────────────────────────

def search_and_play_youtube(query: str) -> str:
    """
    Searches YouTube for the given song or video query and automatically plays the first result.
    Use this when the user asks to play or open a song, music video, or any YouTube content.
    Example: search_and_play_youtube('Bohemian Rhapsody Queen')
    """
    try:
        page = _ensure_browser()
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(2000)

        # Click the first video result
        first_video = page.query_selector("a#video-title")
        if first_video:
            first_video.click()
            page.wait_for_timeout(2000)
            return f"Now playing '{query}' on YouTube, sir."
        else:
            return f"YouTube search for '{query}' is open, but I could not auto-click the first result, sir."
    except Exception as e:
        # Fallback: open in default browser
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        webbrowser.open(url)
        return f"Opened YouTube search for '{query}' in your browser, sir. (Browser automation error: {str(e)})"


# ─── General Browser Navigation ────────────────────────────────────────────

def browser_navigate(url: str) -> str:
    """
    Navigates the automated browser to any URL.
    Use this to open websites like Facebook, Google, Twitter, etc.
    Example: browser_navigate('https://www.facebook.com')
    """
    try:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        page = _ensure_browser()
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1500)
        return f"Navigated to '{url}', sir. The page is now open."
    except Exception as e:
        return f"Error navigating to '{url}': {str(e)}"


def browser_click(text_or_selector: str) -> str:
    """
    Clicks a button, link, or element on the current webpage by its visible text or CSS selector.
    Example: browser_click('Sign Up') or browser_click('Create new account')
    """
    try:
        page = _ensure_browser()
        # Try by visible text first
        try:
            page.get_by_text(text_or_selector, exact=False).first.click(timeout=5000)
            return f"Clicked element with text '{text_or_selector}', sir."
        except Exception:
            pass
        # Try as CSS selector
        page.click(text_or_selector, timeout=5000)
        return f"Clicked element '{text_or_selector}', sir."
    except Exception as e:
        return f"Could not click '{text_or_selector}': {str(e)}"


def browser_type_text(selector_or_label: str, text: str) -> str:
    """
    Finds an input field by its label, placeholder, or CSS selector and types the given text into it.
    Example: browser_type_text('Email', 'john@example.com') or browser_type_text('First name', 'John')
    """
    try:
        page = _ensure_browser()
        # Try by placeholder
        try:
            page.get_by_placeholder(selector_or_label, exact=False).first.fill(text, timeout=5000)
            return f"Typed '{text}' into field '{selector_or_label}', sir."
        except Exception:
            pass
        # Try by label
        try:
            page.get_by_label(selector_or_label, exact=False).first.fill(text, timeout=5000)
            return f"Typed '{text}' into field '{selector_or_label}', sir."
        except Exception:
            pass
        # Try as CSS selector
        page.fill(selector_or_label, text, timeout=5000)
        return f"Typed '{text}' into '{selector_or_label}', sir."
    except Exception as e:
        return f"Could not type into '{selector_or_label}': {str(e)}"


def browser_get_page_text() -> str:
    """
    Returns the visible text content of the current webpage. Use this to read what is on the screen
    before deciding what to click or type next during a multi-step task like filling a form.
    """
    try:
        page = _ensure_browser()
        # Get current URL
        current_url = page.url
        # Get visible text (limit to 3000 chars to avoid overloading the model)
        body_text = page.inner_text("body")[:3000]
        return f"Current URL: {current_url}\n\nPage content:\n{body_text}"
    except Exception as e:
        return f"Error reading page: {str(e)}"


def browser_press_key(key: str) -> str:
    """
    Presses a keyboard key in the browser. Useful for Enter, Tab, Escape, etc.
    Example: browser_press_key('Enter') or browser_press_key('Tab')
    """
    try:
        page = _ensure_browser()
        page.keyboard.press(key)
        page.wait_for_timeout(500)
        return f"Pressed '{key}' key, sir."
    except Exception as e:
        return f"Error pressing key '{key}': {str(e)}"


def browser_close() -> str:
    """Closes the automated browser window."""
    global _browser, _page, _playwright
    with _lock:
        try:
            if _browser:
                _browser.close()
            if _playwright:
                _playwright.stop()
            _browser = None
            _page = None
            _playwright = None
            return "Browser closed, sir."
        except Exception as e:
            return f"Error closing browser: {str(e)}"


BROWSER_TOOLS = [
    search_and_play_youtube,
    browser_navigate,
    browser_click,
    browser_type_text,
    browser_get_page_text,
    browser_press_key,
    browser_close,
]
