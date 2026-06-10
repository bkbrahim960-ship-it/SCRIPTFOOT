import re
from datetime import datetime
from typing import List
from urllib.parse import urljoin

from models import Match, StreamLink
from scraper.base import BaseScraper
from config import config


class GoalHIScraper(BaseScraper):
    name = "goalhi"
    base_urls = [config.goalhi_url]
    enabled = config.enable_goalhi

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
            ".match-box, .match-item, .card-match, "
            ".event-item, .game-box, [class*=match]"
        )

        for container in containers:
            title_el = container.select_one(
                ".match-title, h2, h3, h4, .title, "
                ".team-names, .event-name, [class*=title]"
            )
            if not title_el:
                title_el = container.select_one("a[title]")
                title = title_el["title"] if title_el else None
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
                ".league, .tournament, .competition, "
                ".category, [class*=league]"
            )
            league = league_el.get_text(strip=True) if league_el else None

            time_el = container.select_one(
                ".time, .date, .match-time, [class*=time]"
            )
            match_time = time_el.get_text(strip=True) if time_el else None

            streams = []
            if match_url:
                detail_html = self.get(match_url)
                if detail_html:
                    streams = self.extract_links(detail_html)
                    soup_detail = self.soup(detail_html)
                    player_els = soup_detail.select(
                        "iframe, video source, .stream-player source"
                    )
                    for el in player_els:
                        src = el.get("src") or el.get("data-src")
                        if src:
                            streams.append(StreamLink(url=src, source=self.name))

            channel_els = container.select(
                ".channel, [class*=channel], .tv, .broadcast"
            )
            channels = list(set(
                c.get_text(strip=True) for c in channel_els if c.get_text(strip=True)
            ))

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
        if "live" in text or "مباشر" in text:
            return "live"
        if "انتهى" in text or "final" in text:
            return "finished"
        return "scheduled"
