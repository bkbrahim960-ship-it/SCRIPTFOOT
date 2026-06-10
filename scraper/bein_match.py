import re
from datetime import datetime
from typing import List
from urllib.parse import urljoin

from models import Match, StreamLink
from scraper.base import BaseScraper
from config import config


class BeinMatchScraper(BaseScraper):
    name = "bein_match"
    base_urls = [config.bein_match_url]
    enabled = config.enable_bein_match

    def scrape(self) -> List[Match]:
        all_matches = []
        for base_url in self.base_urls:
            try:
                html = self.get(base_url)
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
            ".match-card, .match-box, .event-item, "
            ".live-item, .game-item, .post-item, "
            "article, [class*=match], [class*=event]"
        )

        for container in containers:
            title_el = container.select_one(
                "h2, h3, h4, .title, .entry-title, "
                ".post-title, a[title], .match-title, "
                ".event-title"
            )
            if not title_el:
                continue

            if title_el.name == "a" and title_el.get("title"):
                title = title_el["title"]
            else:
                title = title_el.get_text(strip=True)

            if not title or len(title) < 5:
                continue

            link_el = container.select_one("a[href]")
            match_url = None
            if link_el:
                href = link_el["href"]
                match_url = href if href.startswith("http") else urljoin(base_url, href)

            league_el = container.select_one(
                ".league, .category, .tournament, "
                ".competition, [class*=league]"
            )
            league = league_el.get_text(strip=True) if league_el else None

            time_el = container.select_one(
                ".date, .time, .match-time, "
                "[class*=time], [class*=date]"
            )
            match_time = time_el.get_text(strip=True) if time_el else None

            status_el = container.select_one(
                ".status, .match-status, .live-tag, "
                "[class*=status], [class*=live]"
            )
            status = "scheduled"
            if status_el:
                st = status_el.get_text(strip=True).lower()
                if "live" in st or "مباشر" in st or "now" in st:
                    status = "live"
                elif "انتهى" in st or "final" in st or "ended" in st:
                    status = "finished"

            channel_els = container.select(
                ".channel, [class*=channel], .tv, .broadcast"
            )
            channels = list(set(
                c.get_text(strip=True) for c in channel_els if c.get_text(strip=True)
            ))

            streams = self.extract_links(html)
            if match_url:
                detail_html = self.get(match_url)
                if detail_html:
                    detail_links = self.extract_links(detail_html)
                    existing = {s.url for s in streams}
                    for dl in detail_links:
                        if dl.url not in existing:
                            streams.append(dl)
                            existing.add(dl.url)

            home_team, away_team = self.extract_teams(title)
            mid = self.make_id(title, match_url or base_url)
            if mid in seen:
                continue
            seen.add(mid)

            match = Match(
                id=mid,
                title=title,
                home_team=home_team,
                away_team=away_team,
                league=league,
                match_time=match_time,
                match_date=datetime.now().strftime("%Y-%m-%d"),
                status=status,
                channels=channels,
                streams=streams,
                source=self.name,
                source_url=match_url or base_url,
            )
            matches.append(match)

        return matches
