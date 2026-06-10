import re
import time
import json
from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote

import httpx
from bs4 import BeautifulSoup

from config import config


class LinkResolver:
    def __init__(self):
        self.client = httpx.Client(
            headers={"User-Agent": config.user_agent},
            timeout=15,
            follow_redirects=True,
            verify=False,
        )

    def resolve(self, url: str, max_depth: int = 5) -> Optional[str]:
        seen = set()
        current = url
        for _ in range(max_depth):
            if current in seen:
                break
            seen.add(current)

            resolved = self._resolve_single(current)
            if not resolved:
                return current

            if self._is_direct_stream(resolved):
                return resolved

            if resolved == current:
                break
            current = resolved

        if self._is_direct_stream(current):
            return current
        return url

    def _resolve_single(self, url: str) -> Optional[str]:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        if "youtube" in domain or "youtu.be" in domain:
            return self._resolve_youtube(url)

        if "watch" in url.lower() or "embed" in url.lower() or "play" in url.lower():
            html = self._fetch(url)
            if html:
                extracted = self._extract_deep(html)
                if extracted:
                    return extracted

        try:
            resp = self.client.head(url, timeout=10)
            location = resp.headers.get("location") or resp.headers.get("Location")
            if location:
                return location if location.startswith("http") else None
        except Exception:
            pass

        html = self._fetch(url)
        if html:
            extracted = self._extract_deep(html)
            if extracted:
                return extracted

        return None

    def _fetch(self, url: str) -> Optional[str]:
        try:
            resp = self.client.get(url, timeout=10)
            return resp.text if resp.status_code == 200 else None
        except Exception:
            return None

    def _extract_deep(self, html: str) -> Optional[str]:
        m3u8 = re.findall(r'https?://[^"\'<>]+\.m3u8[^"\'<>]*', html)
        if m3u8:
            return m3u8[0]

        mp4 = re.findall(r'https?://[^"\'<>]+\.mp4[^"\'<>]*', html)
        if mp4:
            return mp4[0]

        iframe_patterns = re.findall(
            r'<iframe[^>]*src=["\']([^"\']+)["\']', html, re.IGNORECASE
        )
        if iframe_patterns:
            src = iframe_patterns[0]
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = None
            if src and src.startswith("http"):
                return src

        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script"):
            content = script.string or ""
            matches = re.findall(r'(?:src|file|url|link)\s*[:=]\s*["\']([^"\']+\.(?:m3u8|mp4)[^"\']*)["\']', content, re.IGNORECASE)
            if matches:
                return matches[0]
            matches = re.findall(r'https?://[^"\'<>]+\.(?:m3u8|mp4)[^"\'<>]*', content)
            if matches:
                return matches[0]

        return None

    def _is_direct_stream(self, url: str) -> bool:
        return any(ext in url for ext in [".m3u8", ".mp4", ".ts"])

    def _resolve_youtube(self, url: str) -> Optional[str]:
        return url

    def cleanup(self):
        try:
            self.client.close()
        except Exception:
            pass


resolver = LinkResolver()
