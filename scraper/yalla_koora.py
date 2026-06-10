import re
from datetime import datetime
from typing import List

from models import Match, StreamLink
from urllib.parse import urljoin
from scraper.base import BaseScraper
from config import config


class YallaKooraScraper(BaseScraper):
    name = "yalla_koora"
    base_urls = config.yalla_koora_urls
    enabled = config.enable_yalla_koora

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

        cards = soup.select(
            ".match-card, .fixture, .match-item, "
            ".event-box, .match-box, article, "
            "[class*=game], .game-card"
        )

        for card in cards:
            title_el = card.select_one(
                "h2, h3, h4, .match-title, .game-title, "
                ".event-title, [class*=title]"
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            link_el = card.select_one("a[href]")
            match_url = None
            if link_el:
                href = link_el["href"]
                match_url = href if href.startswith("http") else urljoin(base_url, href)

            league_el = card.select_one(
                ".league, .tournament, .competition, "
                "[class*=league], .category"
            )
            league = league_el.get_text(strip=True) if league_el else None

            time_el = card.select_one(
                ".time, .date, .match-time, [class*=time], .event-time"
            )
            match_time = time_el.get_text(strip=True) if time_el else None

            channel_els = card.select(
                ".channel, [class*=channel], .tv, .broadcaster"
            )
            channels = list(set(
                c.get_text(strip=True) for c in channel_els if c.get_text(strip=True)
            ))

            streams = []
            if match_url:
                detail = self.get(match_url)
                if detail:
                    streams = self.extract_links(detail)
                    extra_patterns = re.findall(
                        r'data-src=["\']([^"\']+)["\']', detail
                    )
                    for src in extra_patterns:
                        if src.startswith("http"):
                            streams.append(StreamLink(url=src, source=self.name))

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
                status=self._detect_status(card),
                channels=channels,
                streams=streams,
                source=self.name,
                source_url=match_url or base_url,
            )
            matches.append(match)

        return matches

    def _detect_status(self, card) -> str:
        text = card.get_text().lower()
        if "live" in text or "مباشر" in text or "الآن" in text:
            return "live"
        if "انتهى" in text or "final" in text or "ended" in text:
            return "finished"
        return "scheduled"
