import re
from datetime import datetime
from typing import List, Optional

from models import Match, StreamLink
from scraper.base import BaseScraper
from config import config


class YallaShootScraper(BaseScraper):
    name = "yalla_shoot"
    base_urls = config.yalla_shoot_urls
    enabled = config.enable_yalla_shoot

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
        seen_ids = set()

        match_containers = soup.select(
            ".match-item, .card-match, .match-card, "
            "[class*=match], [class*=Match], "
            "tr:has(.match-date), .event-item, .match-box"
        )

        for container in match_containers:
            title_el = container.select_one(
                ".match-title, .team-name, .match-name, "
                "h2, h3, h4, .title, [class*=title], "
                ".home-team, .away-team, .event-title"
            )
            title = title_el.get_text(strip=True) if title_el else None
            if not title or len(title) < 5:
                continue

            link_el = container.select_one("a[href]")
            match_url = None
            if link_el:
                href = link_el.get("href", "")
                match_url = href if href.startswith("http") else f"{base_url}{href}"

            leagues = container.select_one(
                ".league, .tournament, .championship, "
                "[class*=league], [class*=League], "
                ".competition, .category"
            )
            league = leagues.get_text(strip=True) if leagues else None

            time_el = container.select_one(
                ".time, .match-time, .date, .event-time, "
                "[class*=time], [class*=Time], .start-time"
            )
            match_time = time_el.get_text(strip=True) if time_el else None

            channels = container.select(
                ".channel, .tv-channel, [class*=channel], "
                ".broadcast, .tv, .icon-channel"
            )
            channel_list = list(set(
                ch.get_text(strip=True) for ch in channels if ch.get_text(strip=True)
            ))

            streams = self.extract_links(html)
            if match_url:
                detail_html = self.get(match_url)
                if detail_html:
                    dl = self.extract_links(detail_html)
                    existing = {s.url for s in streams}
                    for s in dl:
                        if s.url not in existing:
                            streams.append(s)
                            existing.add(s.url)

            home_team, away_team = self.extract_teams(title)
            match_id = self.make_id(title, match_url or base_url)

            if match_id in seen_ids:
                continue
            seen_ids.add(match_id)

            match = Match(
                id=match_id,
                title=title,
                home_team=home_team or container.select_one(".home-team, .team-home"),
                away_team=away_team or container.select_one(".away-team, .team-away"),
                league=league,
                match_time=match_time,
                match_date=datetime.now().strftime("%Y-%m-%d"),
                status=self._detect_status(container),
                channels=channel_list,
                streams=streams,
                source=self.name,
                source_url=match_url or base_url,
            )
            if isinstance(match.home_team, str):
                pass
            elif match.home_team:
                match.home_team = match.home_team.get_text(strip=True)

            if isinstance(match.away_team, str):
                pass
            elif match.away_team:
                match.away_team = match.away_team.get_text(strip=True)

            matches.append(match)

        return matches

    def _detect_status(self, container) -> str:
        text = container.get_text().lower()
        if "live" in text or "مباشر" in text or "بث" in text:
            return "live"
        if "انتهت" in text or "ended" in text or "final" in text:
            return "finished"
        return "scheduled"
