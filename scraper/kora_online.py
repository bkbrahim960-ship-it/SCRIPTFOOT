import re
from datetime import datetime
from typing import List
from urllib.parse import urljoin

from models import Match, StreamLink
from scraper.base import BaseScraper
from config import config


class KoraOnlineScraper(BaseScraper):
    name = "kora_online"
    base_urls = [config.kora_online_url]
    enabled = config.enable_kora_online

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
            ".match-item, .event-item, .card, "
            "article, .post, .game-item, "
            "[class*=match], [class*=event]"
        )

        for container in containers:
            title_el = container.select_one(
                "h2, h3, h4, .title, .entry-title, "
                ".post-title, a[title], .match-name"
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
                "[class*=league], .competition"
            )
            league = league_el.get_text(strip=True) if league_el else None

            time_el = container.select_one(
                ".date, .time, .match-time, "
                "[class*=date], [class*=time]"
            )
            match_time = time_el.get_text(strip=True) if time_el else None

            channel_els = container.select(
                ".channel, [class*=channel], .tv-name"
            )
            channels = list(set(
                c.get_text(strip=True) for c in channel_els if c.get_text(strip=True)
            ))

            streams = []
            if match_url:
                detail_html = self.get(match_url)
                if detail_html:
                    streams = self.extract_links(detail_html)

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
                status=self._detect_status(container),
                channels=channels,
                streams=streams,
                source=self.name,
                source_url=match_url or base_url,
            )
            matches.append(match)

        return matches

    def _detect_status(self, container) -> str:
        text = container.get_text().lower()
        if "live" in text or "مباشر" in text or "now" in text:
            return "live"
        if "انتهى" in text or "final" in text:
            return "finished"
        return "scheduled"
