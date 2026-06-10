import hashlib
import re
import random
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from config import config
from models import Match, StreamLink

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
]

CLOUDSCRAPER_AVAILABLE = False
_cloudscraper_session = None
try:
    import cloudscraper
    _cloudscraper_session = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False, "desktop": True},
        delay=1,
    )
    CLOUDSCRAPER_AVAILABLE = True
except Exception:
    CLOUDSCRAPER_AVAILABLE = False
    _cloudscraper_session = None

HTTPX_AVAILABLE = False
try:
    import httpx
    HTTPX_AVAILABLE = True
except Exception:
    HTTPX_AVAILABLE = False

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8,fr;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "DNT": "1",
}


class BaseScraper(ABC):
    name: str = "base"
    base_urls: List[str] = []
    enabled: bool = True

    def __init__(self):
        try:
            self._init_clients()
        except Exception:
            self._httpx = None

    def _init_clients(self):
        ua = random.choice(USER_AGENTS)
        self._cloud = _cloudscraper_session
        self._httpx = None
        if HTTPX_AVAILABLE:
            try:
                self._httpx = httpx.Client(
                    headers={"User-Agent": ua, **HEADERS},
                    timeout=config.request_timeout,
                    follow_redirects=True,
                    verify=False,
                )
            except Exception:
                self._httpx = None

    def get(self, url: str) -> Optional[str]:
        if CLOUDSCRAPER_AVAILABLE and self._cloud:
            try:
                resp = self._cloud.get(url, timeout=config.request_timeout)
                if resp.status_code == 200 and len(resp.text) > 500:
                    return resp.text
            except Exception:
                pass
        if HTTPX_AVAILABLE and self._httpx:
            try:
                resp = self._httpx.get(url)
                if resp.status_code == 200 and len(resp.text) > 500:
                    return resp.text
            except Exception:
                pass
        if HTTPX_AVAILABLE:
            try:
                new_ua = random.choice(USER_AGENTS)
                fresh = httpx.Client(
                    headers={"User-Agent": new_ua, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
                    timeout=15, follow_redirects=True, verify=False,
                )
                resp = fresh.get(url)
                fresh.close()
                if resp.status_code == 200 and len(resp.text) > 500:
                    return resp.text
            except Exception:
                pass
        return None

    def soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    @abstractmethod
    def scrape(self) -> List[Match]:
        ...

    def make_id(self, title: str, url: str) -> str:
        raw = f"{self.name}:{title}:{url}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def extract_iframe_src(self, html: str) -> List[str]:
        soup = self.soup(html)
        urls = []
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src")
            if src and src.startswith("http"):
                urls.append(src)
        return urls

    def extract_m3u8(self, html: str) -> List[str]:
        return list(set(re.findall(r'https?://[^"\'\s]+\.m3u8[^"\'\s]*', html)))

    def extract_mp4(self, html: str) -> List[str]:
        return list(set(re.findall(r'https?://[^"\'\s]+\.mp4[^"\'\s]*', html)))

    EXTERNAL_PLAYERS = [
        "youtube.com/embed", "youtube.com/watch", "youtu.be",
        "vidmoly", "gounlimited", "streamtape", "doodstream",
        "dood.ws", "dood.la", "mixdrop", "upstream",
        "embed", "player.", "play.", "cdn.", "stream.",
        "ok.ru", "vk.com", "facebook.com/watch",
        "mega.nz", "google drive", "drive.google",
        "hls.", "mp4.", "m3u8",
    ]

    def extract_links(self, html: str, use_resolver: bool = True) -> List[StreamLink]:
        links = []
        seen = set()

        for url in self.extract_m3u8(html):
            if url not in seen:
                seen.add(url)
                links.append(StreamLink(url=url, source=self.name, is_verified=True))

        for url in self.extract_mp4(html):
            if url not in seen:
                seen.add(url)
                links.append(StreamLink(url=url, source=self.name, is_verified=True))

        iframe_urls = self.extract_iframe_src(html)
        for url in iframe_urls:
            if url not in seen:
                seen.add(url)
                links.append(StreamLink(url=url, source=self.name))

        script_links = self._extract_from_scripts(html)
        for url in script_links:
            if url not in seen:
                seen.add(url)
                links.append(StreamLink(url=url, source=self.name, is_verified=True))

        player_links = self._extract_player_links(html)
        for url in player_links:
            if url not in seen:
                seen.add(url)
                links.append(StreamLink(url=url, source=self.name))

        data_links = self._extract_from_data_attrs(html)
        for url in data_links:
            if url not in seen:
                seen.add(url)
                links.append(StreamLink(url=url, source=self.name))

        embed_links = self._extract_embeds(html)
        for url in embed_links:
            if url not in seen:
                seen.add(url)
                links.append(StreamLink(url=url, source=self.name))

        return links

    def _extract_player_links(self, html: str) -> List[str]:
        found = set()
        for pattern in self.EXTERNAL_PLAYERS:
            regex = rf'https?://[^"\'<>]*(?:{re.escape(pattern)})[^"\'<>]*'
            for m in re.finditer(regex, html):
                url = m.group(0).split("&")[0].strip()
                if url.startswith("http"):
                    found.add(url)
            for m in re.finditer(re.escape(pattern), html, re.IGNORECASE):
                idx = m.start()
                for prefix in ["src=", "href=", "data-src=", "data-url=", 'url: "', 'source: "', 'file: "', 'link: "']:
                    start = html.rfind(prefix, max(0, idx-500), idx)
                    if start != -1:
                        end = html.find('"', start + len(prefix))
                        if end != -1:
                            val = html[start+len(prefix):end]
                            if val.startswith("http") or val.startswith("//"):
                                if val.startswith("//"):
                                    val = "https:" + val
                                found.add(val)
        return list(found)

    def _extract_from_data_attrs(self, html: str) -> List[str]:
        found = set()
        for attr in ["data-src", "data-url", "data-link", "data-href",
                      "data-live", "data-stream", "data-video", "data-embed",
                      "data-player", "data-file", "data-source"]:
            for m in re.finditer(rf'{re.escape(attr)}=["\']([^"\']+)["\']', html):
                val = m.group(1)
                if val.startswith("http") or val.startswith("//"):
                    if val.startswith("//"):
                        val = "https:" + val
                    found.add(val)
        return list(found)

    def _extract_embeds(self, html: str) -> List[str]:
        found = set()
        patterns = [
            r'embed[^"\']*["\']([^"\']+)["\']',
            r'player[^"\']*["\']([^"\']+)["\']',
            r'watch[^"\']*["\']([^"\']+)["\']',
            r'live[^"\']*["\']([^"\']+)["\']',
            r'stream[^"\']*["\']([^"\']+)["\']',
        ]
        for pat in patterns:
            for m in re.finditer(pat, html):
                val = m.group(1)
                if val.startswith("http") or val.startswith("//"):
                    if val.startswith("//"):
                        val = "https:" + val
                    found.add(val)
        return list(found)

    def _maybe_resolve(self, url: str) -> str:
        try:
            from scraper.link_resolver import resolver
            return resolver.resolve(url)
        except Exception:
            return url

    def _extract_from_scripts(self, html: str) -> List[str]:
        soup = self.soup(html)
        urls = []
        for script in soup.find_all("script"):
            content = script.string or ""
            patterns = re.findall(
                r'(?:src|file|url|link|playlist)\s*[:=]\s*["\']([^"\']+\.(?:m3u8|mp4)[^"\']*)["\']',
                content, re.IGNORECASE
            )
            urls.extend(patterns)
            patterns = re.findall(r'https?://[^"\'<>\s]+\.(?:m3u8|mp4)[^"\'<>\s]*', content)
            urls.extend(patterns)

            for match in re.finditer(r'["\']([^"\']*(?:m3u8|mp4|playlist)[^"\']*)["\']', content):
                u = match.group(1)
                if u.startswith("http"):
                    urls.append(u)
        return list(set(urls))

    def _guess_quality(self, url: str) -> Optional[str]:
        q = re.search(r'(\d{3,4})p', url, re.IGNORECASE)
        return f"{q.group(1)}p" if q else None

    def clean_title(self, title: str) -> str:
        prefixes = ["مباراة ", "مشاهدة ", "بث مباشر ", "بث ", "مباشر ", "ماتش ",
                     "live ", "watch ", "stream "]
        t = title.strip()
        for p in prefixes:
            while t.startswith(p):
                t = t[len(p):]
        suffixes = [" بث مباشر", " مشاهدة", " مباشر", " اليوم", " الان",
                     " live", " stream", " watch", " hd", " 4k"]
        for s in suffixes:
            if t.endswith(s):
                t = t[:-len(s)]
        source_names = ["bein match", "yalla shoot", "yalla koora", "goalhi",
                        "kora online", "akwam", "mashahd", "3sate",
                        "بي إن ماتش", "يلا شوت", "يلا كورة", "كورة اونلاين",
                        "بي ان ماتش", "goalhi"]
        t_lower = t.lower()
        for src in source_names:
            if src in t_lower:
                idx = t_lower.index(src)
                t = t[:idx].strip()
                if t.endswith(","):
                    t = t[:-1].strip()
        parts = t.split(" – ")
        if len(parts) > 1:
            t = parts[0].strip()
        parts = t.split(" - ")
        if len(parts) > 1:
            t = parts[0].strip()
        return t.strip()

    def extract_teams(self, title: str):
        if not title:
            return None, None
        title = self.clean_title(title)
        separators = [" و", " vs ", " VS ", " – ", " - ", " — ", " ضد ", " x ", " X "]
        for sep in separators:
            if sep in title:
                parts = title.split(sep, 1)
                t1 = parts[0].strip().strip("،,")
                t2 = parts[1].strip().strip("،,")
                if t1 and t2 and len(t1) > 1 and len(t2) > 1:
                    return t1, t2
        return None, None

    def parse_match_date(self, date_text: str, time_text: str = "") -> tuple:
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = time_text or ""

        if not date_text:
            return (date_str, time_str)

        dt = date_text.strip()
        tl = time_text.strip()

        if "غداً" in dt or "غدا" in dt or "tomorrow" in dt.lower():
            tomorrow = now + timedelta(days=1)
            date_str = tomorrow.strftime("%Y-%m-%d")
        elif "بعد غد" in dt or "after tomorrow" in dt.lower():
            after = now + timedelta(days=2)
            date_str = after.strftime("%Y-%m-%d")
        else:
            patterns = [
                r"(\d{4})-(\d{1,2})-(\d{1,2})",
                r"(\d{1,2})-(\d{1,2})-(\d{4})",
                r"(\d{1,2})/(\d{1,2})/(\d{4})",
                r"(\d{1,2})\s+(\d{1,2})\s+(\d{4})",
            ]
            for pat in patterns:
                m = re.search(pat, dt)
                if m:
                    g = m.groups()
                    if len(g[0]) == 4:
                        date_str = f"{g[0]}-{g[1].zfill(2)}-{g[2].zfill(2)}"
                    else:
                        date_str = f"{g[2]}-{g[0].zfill(2)}-{g[1].zfill(2)}"
                    break

        time_patterns = [
            r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?",
            r"(\d{1,2})\s*(AM|PM|am|pm)",
        ]
        for pat in time_patterns:
            m = re.search(pat, tl)
            if m:
                time_str = m.group(0).strip()
                break

        return (date_str, time_str)

    def compute_status_ar(self, match_date: str, match_time: str, page_status: str) -> str:
        if page_status == "live":
            return "مباشر الآن"
        if page_status == "finished":
            return "انتهت"

        now = datetime.now()
        try:
            if match_date:
                parts = match_date.split("-")
                if len(parts) == 3:
                    md = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
                    if md < now.replace(hour=0, minute=0, second=0):
                        return "انتهت"
                    if md > now.replace(hour=0, minute=0, second=0):
                        return "لم تبدأ"
                    if md == now.replace(hour=0, minute=0, second=0):
                        return "اليوم"
        except Exception:
            pass

        if page_status == "scheduled":
            return "لم تبدأ"
        return "لم تبدأ"

    def cleanup(self):
        try:
            self.client.close()
        except Exception:
            pass
