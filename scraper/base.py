import hashlib
import re
from abc import ABC, abstractmethod
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from config import config
from models import Match, StreamLink


class BaseScraper(ABC):
    name: str = "base"
    base_urls: List[str] = []
    enabled: bool = True

    def __init__(self):
        self.client = httpx.Client(
            headers={"User-Agent": config.user_agent},
            timeout=config.request_timeout,
            follow_redirects=True,
            verify=False,
        )

    def get(self, url: str) -> Optional[str]:
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"[{self.name}] GET failed {url}: {e}")
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

    def extract_links(self, html: str, use_resolver: bool = True) -> List[StreamLink]:
        links = []
        seen = set()

        for url in self.extract_m3u8(html):
            final = self._maybe_resolve(url) if use_resolver else url
            if final not in seen:
                seen.add(final)
                links.append(StreamLink(
                    url=final, quality=self._guess_quality(final),
                    source=self.name, is_verified=True
                ))

        for url in self.extract_mp4(html):
            final = self._maybe_resolve(url) if use_resolver else url
            if final not in seen:
                seen.add(final)
                links.append(StreamLink(
                    url=final, quality=self._guess_quality(final),
                    source=self.name, is_verified=True
                ))

        iframe_urls = self.extract_iframe_src(html)
        for url in iframe_urls:
            if url not in seen:
                seen.add(url)
                links.append(StreamLink(url=url, source=self.name))

        script_links = self._extract_from_scripts(html)
        for url in script_links:
            final = self._maybe_resolve(url) if use_resolver else url
            if final not in seen:
                seen.add(final)
                links.append(StreamLink(
                    url=final, quality=self._guess_quality(final),
                    source=self.name, is_verified=True
                ))

        return links

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

    def cleanup(self):
        try:
            self.client.close()
        except Exception:
            pass
