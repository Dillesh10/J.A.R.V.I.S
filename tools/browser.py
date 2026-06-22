import os
import urllib.parse
import webbrowser
import threading
from pydantic import BaseModel, Field
from tools.base import BaseTool
from tools.registry import register_tool

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
            import importlib
            playwright_sync = importlib.import_module("playwright.sync_api")
            sync_playwright = playwright_sync.sync_playwright
            _playwright = sync_playwright().start()
            _browser = _playwright.chromium.launch(headless=False, slow_mo=100)
            _page = _browser.new_page()
            _page.set_viewport_size({"width": 1280, "height": 800})
    return _page

# ─── BROWSER NAVIGATION TOOL ──────────────────────────────────────────────────

class BrowserNavigateSchema(BaseModel):
    url: str = Field(description="The website URL to navigate to (e.g. 'https://google.com').")

@register_tool
class BrowserNavigateTool(BaseTool):
    name = "browser_navigate"
    description = "Navigates the automated browser to any URL. Use this to open websites."
    permissions = ["read", "execute"]
    args_schema = BrowserNavigateSchema

    def execute(self, url: str) -> str:
        if os.environ.get("VERCEL") == "1":
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
            return f"I am running in the cloud (Vercel), sir. I have opened the URL '{url}' in your default browser. OPEN_URL:{url}"
        try:
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
            page = _ensure_browser()
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1500)
            return f"Navigated to '{url}', sir. The page is now open."
        except Exception as e:
            return f"Error navigating to '{url}': {str(e)}"

# ─── BROWSER CLICK TOOL ───────────────────────────────────────────────────────

class BrowserClickSchema(BaseModel):
    text_or_selector: str = Field(description="The visible button/link text or CSS selector to click.")

@register_tool
class BrowserClickTool(BaseTool):
    name = "browser_click"
    description = "Clicks a button, link, or element on the current webpage by text or CSS selector."
    permissions = ["execute"]
    args_schema = BrowserClickSchema

    def execute(self, text_or_selector: str) -> str:
        if os.environ.get("VERCEL") == "1":
            return "I am running in the cloud (Vercel), sir. Browser click actions are only available locally."
        try:
            page = _ensure_browser()
            try:
                page.get_by_text(text_or_selector, exact=False).first.click(timeout=5000)
                return f"Clicked element with text '{text_or_selector}', sir."
            except Exception:
                pass
            page.click(text_or_selector, timeout=5000)
            return f"Clicked element '{text_or_selector}', sir."
        except Exception as e:
            return f"Could not click '{text_or_selector}': {str(e)}"

# ─── BROWSER TYPE TEXT TOOL ───────────────────────────────────────────────────

class BrowserTypeTextSchema(BaseModel):
    selector_or_label: str = Field(description="The input field's label, placeholder, or CSS selector.")
    text: str = Field(description="The text content to type into the field.")

@register_tool
class BrowserTypeTextTool(BaseTool):
    name = "browser_type_text"
    description = "Types text into a form input field (found by label, placeholder, or selector)."
    permissions = ["execute"]
    args_schema = BrowserTypeTextSchema

    def execute(self, selector_or_label: str, text: str) -> str:
        if os.environ.get("VERCEL") == "1":
            return "I am running in the cloud (Vercel), sir. Browser typing actions are only available locally."
        try:
            page = _ensure_browser()
            try:
                page.get_by_placeholder(selector_or_label, exact=False).first.fill(text, timeout=5000)
                return f"Typed '{text}' into field '{selector_or_label}', sir."
            except Exception:
                pass
            try:
                page.get_by_label(selector_or_label, exact=False).first.fill(text, timeout=5000)
                return f"Typed '{text}' into field '{selector_or_label}', sir."
            except Exception:
                pass
            page.fill(selector_or_label, text, timeout=5000)
            return f"Typed '{text}' into '{selector_or_label}', sir."
        except Exception as e:
            return f"Could not type into '{selector_or_label}': {str(e)}"

# ─── BROWSER GET PAGE TEXT TOOL ───────────────────────────────────────────────

@register_tool
class BrowserGetPageTextTool(BaseTool):
    name = "browser_get_page_text"
    description = "Returns the visible text content of the current webpage for understanding the page."
    permissions = ["read"]

    def execute(self) -> str:
        if os.environ.get("VERCEL") == "1":
            return "I am running in the cloud (Vercel), sir. Browser reading actions are only available locally."
        try:
            page = _ensure_browser()
            current_url = page.url
            body_text = page.inner_text("body")[:3000]
            return f"Current URL: {current_url}\n\nPage content:\n{body_text}"
        except Exception as e:
            return f"Error reading page: {str(e)}"

# ─── BROWSER PRESS KEY TOOL ───────────────────────────────────────────────────

class BrowserPressKeySchema(BaseModel):
    key: str = Field(description="The key name to press (e.g. 'Enter', 'Tab', 'Escape').")

@register_tool
class BrowserPressKeyTool(BaseTool):
    name = "browser_press_key"
    description = "Presses a keyboard key in the browser session."
    permissions = ["execute"]
    args_schema = BrowserPressKeySchema

    def execute(self, key: str) -> str:
        if os.environ.get("VERCEL") == "1":
            return "I am running in the cloud (Vercel), sir. Browser keypress events are only available locally."
        try:
            page = _ensure_browser()
            page.keyboard.press(key)
            page.wait_for_timeout(500)
            return f"Pressed '{key}' key, sir."
        except Exception as e:
            return f"Error pressing key '{key}': {str(e)}"

# ─── BROWSER CLOSE TOOL ───────────────────────────────────────────────────────

@register_tool
class BrowserCloseTool(BaseTool):
    name = "browser_close"
    description = "Closes the automated Playwright browser session."
    permissions = ["execute"]

    def execute(self) -> str:
        if os.environ.get("VERCEL") == "1":
            return "I am running in the cloud (Vercel), sir. Browser controls are unavailable."
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

# ─── YOUTUBE PLAY TOOL ────────────────────────────────────────────────────────

class SearchPlayYoutubeSchema(BaseModel):
    query: str = Field(description="Song name or search term to play (e.g. 'Queen Bohemian Rhapsody').")

@register_tool
class SearchPlayYoutubeTool(BaseTool):
    name = "search_and_play_youtube"
    description = "Searches YouTube and auto-plays the first video result. Use for all song or video requests."
    permissions = ["read", "execute"]
    args_schema = SearchPlayYoutubeSchema

    def execute(self, query: str) -> str:
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        if os.environ.get("VERCEL") == "1":
            return f"I am running in the cloud (Vercel), sir. I have opened the YouTube search for '{query}' on your browser. OPEN_URL:{url}"
        try:
            page = _ensure_browser()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            first_video = page.query_selector("a#video-title")
            if first_video:
                first_video.click()
                page.wait_for_timeout(2000)
                video_url = page.url
                return f"Now playing '{query}' on YouTube, sir. OPEN_URL:{video_url}"
            else:
                return f"YouTube search for '{query}' is open, but I could not auto-click the first result. sir. OPEN_URL:{url}"
        except Exception as e:
            webbrowser.open(url)
            return f"Opened YouTube search for '{query}' in your browser, sir. OPEN_URL:{url} (Browser automation error: {str(e)})"
