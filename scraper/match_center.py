import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

from models import Match, StreamLink
from scraper.base import BaseScraper


class MatchCenterScraper(BaseScraper):
    name = "match_center"
    base_urls = [
        "https://www.yallakora.com",
        "https://www.kooora.com",
    ]
    enabled = True

    def scrape(self) -> List[Match]:
        all_matches = []
        for base_url in self.base_urls:
            try:
                for endpoint in ["/match-center", "/live", "/matches"]:
                    html = self.get(f"{base_url}{endpoint}")
                    if html:
                        matches = self._parse_matches(html, base_url)
                        if matches:
                            all_matches.extend(matches)
                            print(f"[{self.name}] {base_url}{endpoint}: {len(matches)} clean matches")
                            break
            except Exception as e:
                print(f"[{self.name}] Error: {e}")
        return all_matches

    def _parse_matches(self, html: str, base_url: str) -> List[Match]:
        soup = self.soup(html)
        matches = []
        seen = set()

        containers = soup.select(
            ".match-item, .match-card, .fixture, .match-box, "
            ".match-event, tr.match, .live-match, "
            ".schedule-match, .match-row, .match-fixture, "
            ".match-info, .match-wrapper, "
            "[class*=match], [class*=fixture]"
        )

        for container in containers:
            m = self._extract_match(container, base_url)
            if m and m.id not in seen:
                seen.add(m.id)
                matches.append(m)

        return matches

    def _extract_match(self, container, base_url: str) -> Optional[Match]:
        title_el = container.select_one(
            "h2, h3, h4, .title, .match-title, .team-names, "
            ".match-name, [class*=title], a[title]"
        )
        if not title_el:
            return None

        title = title_el.get("title") or title_el.get_text(strip=True) if title_el.name == "a" else title_el.get_text(strip=True)
        if not title or len(title) < 5:
            return None

        home_el = container.select_one(
            ".home-team, .team-home, .home, .team-a, "
            "[class*=home], .match-home, .home-name"
        )
        away_el = container.select_one(
            ".away-team, .team-away, .away, .team-b, "
            "[class*=away], .match-away, .away-name"
        )

        home_team = home_el.get_text(strip=True) if home_el else None
        away_team = away_el.get_text(strip=True) if away_el else None

        if not home_team or not away_team:
            home_team, away_team = self.extract_teams(title)

        link_el = container.select_one("a[href]")
        match_url = None
        if link_el:
            href = link_el["href"]
            match_url = href if href.startswith("http") else urljoin(base_url, href)

        league_el = container.select_one(
            ".league, .tournament, .competition, .category, "
            "[class*=league], .match-league, .championship"
        )
        league = league_el.get_text(strip=True) if league_el else None

        time_el = container.select_one(
            ".time, .date, .match-time, .start-time, "
            "[class*=time], [class*=date], .event-time, .match-date"
        )
        match_time = time_el.get_text(strip=True) if time_el else None

        score_el = container.select_one(
            ".score, .result, .match-score, [class*=score]"
        )
        score = score_el.get_text(strip=True) if score_el else None

        status = self._detect_status(container)

        parsed_date, parsed_time = self.parse_match_date(
            date_text=league or match_time or "",
            time_text=match_time or ""
        )
        if parsed_time:
            match_time = parsed_time

        streams = self.extract_links(html)
        if match_url:
            detail = self.get(match_url)
            if detail:
                dl = self.extract_links(detail)
                existing = {s.url for s in streams}
                for s in dl:
                    if s.url not in existing:
                        streams.append(s)
                        existing.add(s.url)

        channel_els = container.select(
            ".channel, [class*=channel], .tv, .broadcast, .tv-channel"
        )
        channels = list(set(
            c.get_text(strip=True) for c in channel_els if c.get_text(strip=True)
        ))

        mid = self.make_id(title, match_url or base_url)
        return Match(
            id=mid, title=title or f"{home_team} vs {away_team}",
            home_team=home_team, away_team=away_team,
            league=league, score=score,
            match_time=match_time, match_date=parsed_date,
            status=status, channels=channels,
            streams=streams,
            source=self.name,
            source_url=match_url or base_url,
        )

    def _detect_status(self, container) -> str:
        text = container.get_text().lower()
        if any(w in text for w in ["live", "مباشر", "now", "الآن"]):
            return "live"
        status_el = container.select_one(
            ".status, .match-status, [class*=status], .live-tag"
        )
        if status_el:
            st = status_el.get_text(strip=True).lower()
            if "live" in st or "مباشر" in st:
                return "live"
            if "ended" in st or "انتهى" in st or "final" in st:
                return "finished"
        if "انتهت" in text or "final" in text or "ended" in text:
            return "finished"
        score_el = container.select_one(
            ".score, .result, [class*=score]"
        )
        if score_el:
            s = score_el.get_text(strip=True)
            if s and "-" in s:
                if ":" not in container.get_text():
                    return "finished"
        return "scheduled"
