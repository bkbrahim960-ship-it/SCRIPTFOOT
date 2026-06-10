import threading
from typing import Optional

PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass


class PlaywrightMixin:
    _browser: Optional[object] = None
    _lock = threading.Lock()
    _disabled = False

    @classmethod
    def is_available(cls) -> bool:
        return PLAYWRIGHT_AVAILABLE and not cls._disabled

    @classmethod
    def get_browser(cls):
        if not cls.is_available():
            return None
        if cls._browser is None:
            with cls._lock:
                if cls._browser is None:
                    try:
                        p = sync_playwright().start()
                        cls._browser = p.chromium.launch(
                            headless=True,
                            args=[
                                "--no-sandbox",
                                "--disable-setuid-sandbox",
                                "--disable-dev-shm-usage",
                                "--disable-gpu",
                                "--disable-web-security",
                                "--disable-features=IsolateOrigins,site-per-process",
                            ]
                        )
                    except Exception as e:
                        print(f"[Playwright] Launch failed, disabling: {e}")
                        cls._disabled = True
                        return None
        return cls._browser

    def render_page(self, url: str, timeout: int = 15000) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            browser = self.get_browser()
            if not browser:
                return None
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="ar",
                extra_http_headers={
                    "Accept-Language": "ar,en;q=0.9",
                    "Referer": "https://www.google.com/",
                }
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(3000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            html = page.content()
            context.close()
            return html
        except Exception as e:
            print(f"[Playwright] Error rendering {url}: {e}")
            return None

    def wait_and_get_source(self, url: str, selector: str = "body", timeout: int = 20000) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            browser = self.get_browser()
            if not browser:
                return None
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="ar",
            )
            page = context.new_page()
            page.route("**/*", self._block_unnecessary)
            page.goto(url, wait_until="networkidle", timeout=timeout)
            try:
                page.wait_for_selector(selector, timeout=5000)
            except Exception:
                pass
            html = page.content()
            context.close()
            return html
        except Exception as e:
            print(f"[Playwright] Error waiting for {url}: {e}")
            return None

    def _block_unnecessary(self, route):
        blocked = [".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ttf", ".mp4"]
        if any(route.request.url.endswith(ext) for ext in blocked):
            route.abort()
        else:
            route.continue_()

    def extract_m3u8_from_network(self, url: str, timeout: int = 20000) -> list:
        if not self.is_available():
            return []
        m3u8_urls = []
        try:
            browser = self.get_browser()
            if not browser:
                return []
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()

            def handle_response(response):
                if ".m3u8" in response.url:
                    m3u8_urls.append(response.url)

            page.on("response", handle_response)
            page.goto(url, wait_until="networkidle", timeout=timeout)
            page.wait_for_timeout(5000)
            context.close()
        except Exception as e:
            print(f"[Playwright] Network capture error: {e}")
        return list(set(m3u8_urls))

    @classmethod
    def cleanup_browser(cls):
        if cls._browser:
            try:
                cls._browser.close()
            except Exception:
                pass
            cls._browser = None
