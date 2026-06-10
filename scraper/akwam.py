import re
from datetime import datetime
from typing import List
from urllib.parse import urljoin

from models import Match, StreamLink
from scraper.base import BaseScraper
from scraper.playwright_mixin import PlaywrightMixin
from scraper.link_resolver import resolver


class AkwamScraper(BaseScraper, PlaywrightMixin):
    name = "akwam"
    base_urls = [
        "https://akwam.to",
        "https://ak.si",
    ]
    enabled = True

    def scrape(self) -> List[Match]:
        all_matches = []
        for base_url in self.base_urls:
            try:
                html = self.render_page(base_url, timeout=20000)
                if not html:
                    continue
                matches = self._parse_matches(html, base_url)
                all_matches.extend(matches)
                print(f"[{self.name}] {base_url}: {len(matches)} matches")
            except Exception as e:
                print(f"[{self.name}] Error scraping {base_url}: {e}")
        return all_matches

    def _parse_matches(self, html: str, base_url: str) -> List[Match]:
        soup = self.soup(html)
        matches = []
        seen = set()

        containers = soup.select(
            ".card, .post-card, .item, article, "
            ".movie-card, .video-card, [class*=post], "
            "[class*=card]"
        )

        for container in containers:
            title_el = container.select_one(
                "h2, h3, h4, .title, .post-title, "
                ".entry-title, a[title], .card-title"
            )
            link_el = container.select_one("a[href]")

            if not title_el or not link_el:
                continue

            if title_el.name == "a" and title_el.get("title"):
                title = title_el["title"]
            else:
                title = title_el.get_text(strip=True)

            if not title or len(title) < 5:
                continue

            href = link_el["href"]
            match_url = href if href.startswith("http") else urljoin(base_url, href)

            if not self._is_football(title):
                continue

            streams = []
            detail_html = self.wait_and_get_source(match_url, selector=".video-js", timeout=25000)
            if detail_html:
                raw_links = self.extract_links(detail_html)
                network_m3u8 = self.extract_m3u8_from_network(match_url, timeout=15000)
                seen_urls = set()
                for link in raw_links:
                    final = resolver.resolve(link.url)
                    if final not in seen_urls:
                        seen_urls.add(final)
                        streams.append(StreamLink(
                            url=final, quality=link.quality,
                            source=self.name, is_verified=True
                        ))
                for u in network_m3u8:
                    if u not in seen_urls:
                        seen_urls.add(u)
                        streams.append(StreamLink(
                            url=u, source=self.name, is_verified=True
                        ))

            home_team, away_team = self.extract_teams(title)
            mid = self.make_id(title, match_url)
            if mid in seen:
                continue
            seen.add(mid)

            match = Match(
                id=mid, title=title,
                home_team=home_team, away_team=away_team,
                match_time=datetime.now().strftime("%H:%M"),
                match_date=datetime.now().strftime("%Y-%m-%d"),
                status="live" if "live" in title.lower() or "مباشر" in title else "scheduled",
                streams=streams,
                source=self.name,
                source_url=match_url,
            )
            matches.append(match)

        return matches

    def _is_football(self, title: str) -> bool:
        keywords = [
            "كرة", "football", "soccer", "مباراة", "match", "الدوري",
            "champions", "league", "كأس", "cup", " UEFA ", " FIFA ",
            "الاهلي", "الهلال", "النصر", "الاتحاد", "الزمالك", "برشلونة",
            "ريال", "مدريد", "بايرن", "ليفربول", "مانشستر", "تشيلسي",
            "ارسنال", "توتنهام", "يوفنتوس", "ميلان", "انتر", "باريس",
            "psg", "juventus", "liverpool", "manchester", "barcelona",
            "real madrid", "bayern", "chelsea", "arsenal", "tottenham",
        ]
        t = title.lower()
        return any(kw in t for kw in keywords)
