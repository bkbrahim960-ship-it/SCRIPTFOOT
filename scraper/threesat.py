import re
from datetime import datetime
from typing import List
from urllib.parse import urljoin

from models import Match, StreamLink
from scraper.base import BaseScraper
from scraper.playwright_mixin import PlaywrightMixin
from scraper.link_resolver import resolver


class ThreeSatScraper(BaseScraper, PlaywrightMixin):
    name = "3sate"
    base_urls = [
        "https://3sate.com",
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
            ".match, .game, .event, .live, "
            ".match-item, .card, article, "
            "[class*=match], [class*=live], [class*=game]"
        )

        for container in containers:
            title_el = container.select_one(
                "h2, h3, h4, .title, .match-title, "
                ".event-title, a[title]"
            )
            link_el = container.select_one("a[href]")

            if not title_el or not link_el:
                continue

            title = (title_el.get("title") or title_el.get_text(strip=True))
            if not title or len(title) < 5:
                continue

            href = link_el["href"]
            match_url = href if href.startswith("http") else urljoin(base_url, href)

            league_el = container.select_one(
                ".league, .category, .tournament, "
                ".competition, [class*=league]"
            )
            league = league_el.get_text(strip=True) if league_el else None

            channel_els = container.select(
                ".channel, [class*=channel], .tv-name"
            )
            channels = list(set(
                c.get_text(strip=True) for c in channel_els if c.get_text(strip=True)
            ))

            status = self._detect_status(container)
            streams = []

            if status == "live" or status == "scheduled":
                detail_html = self.wait_and_get_source(match_url, timeout=20000)
                if detail_html:
                    extracted = self.extract_links(detail_html)
                    network = self.extract_m3u8_from_network(match_url, timeout=15000)
                    seen_urls = set()
                    for link in extracted:
                        final = resolver.resolve(link.url)
                        if final not in seen_urls:
                            seen_urls.add(final)
                            streams.append(StreamLink(
                                url=final, quality=link.quality,
                                source=self.name, is_verified=True
                            ))
                    for u in network:
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
                league=league, channels=channels,
                match_time=datetime.now().strftime("%H:%M"),
                match_date=datetime.now().strftime("%Y-%m-%d"),
                status=status, streams=streams,
                source=self.name,
                source_url=match_url,
            )
            matches.append(match)

        return matches

    def _detect_status(self, container) -> str:
        text = container.get_text().lower()
        if "live" in text or "مباشر" in text or "بث" in text:
            return "live"
        if "انتهى" in text or "final" in text:
            return "finished"
        return "scheduled"
