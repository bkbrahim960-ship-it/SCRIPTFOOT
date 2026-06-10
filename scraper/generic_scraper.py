import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

from models import Match, StreamLink
from scraper.base import BaseScraper
from scraper.sources_list import SOURCES

MATCH_SELECTORS = [
    ".match-item", ".match-card", ".card-match", ".match-box",
    ".event-item", ".game-item", ".game-card", ".fixture",
    ".match", ".event", ".game", ".live-match", ".live-game",
    ".post-item", "article.post", ".item-match", ".match-row",
    ".match-event", ".match-fixture", ".live-item",
    "tr.match", "[class*=match]", "[class*=Match]",
    "[class*=game]", "[class*=event]", "[class*=fixture]",
    ".v2-match", ".match-info", ".match-block",
]

TITLE_SELECTORS = [
    "h2", "h3", "h4", ".title", ".match-title", ".event-title",
    ".game-title", ".post-title", ".entry-title", ".card-title",
    "a[title]", ".match-name", ".event-name", ".game-name",
    "[class*=title]", "[class*=name]",
]

LINK_SELECTORS = [
    "a[href*='/match/']", "a[href*='/live/']", "a[href*='/game/']",
    "a[href*='/event/']", "a[href*='/watch/']", "a[href*='/stream/']",
    "a[href*='match']", "a[href*='live']", "a[href*='game']",
    "a[href*='event']", "a[href*='/tv/']",
]

LEAGUE_SELECTORS = [
    ".league", ".tournament", ".competition", ".category",
    "[class*=league]", "[class*=tournament]", "[class*=competition]",
]

TIME_SELECTORS = [
    ".time", ".date", ".match-time", ".event-time", ".game-time",
    ".start-time", "[class*=time]", "[class*=date]",
    ".match-date", ".event-date",
]

CHANNEL_SELECTORS = [
    ".channel", "[class*=channel]", ".tv", ".broadcast",
    ".tv-channel", ".broadcaster", "[class*=tv]",
]

STATUS_SELECTORS = [
    ".status", ".match-status", ".live-tag", ".live-label",
    "[class*=status]", "[class*=live]",
]


class GenericScraper(BaseScraper):
    name = "generic"
    enabled = True

    def __init__(self):
        super().__init__()
        self.sites_to_scrape = [s for s in SOURCES if s["type"] in ("generic", "rss", "telegram", "iptv")]

    def scrape(self) -> List[Match]:
        all_matches = []
        for site in self.sites_to_scrape:
            try:
                site_matches = self._scrape_site(site)
                all_matches.extend(site_matches)
                if site_matches:
                    print(f"[{self.name}] {site['name']}: {len(site_matches)} matches")
            except Exception as e:
                pass
        return all_matches

    def _scrape_site(self, site: dict) -> List[Match]:
        stype = site["type"]
        url = site["url"]

        if stype == "rss":
            return self._scrape_rss(url, site["name"])
        elif stype == "telegram":
            return self._scrape_telegram(url, site["name"])
        elif stype == "iptv":
            return self._scrape_iptv(url, site["name"])
        else:
            return self._scrape_generic(url, site["name"])

    def _scrape_generic(self, url: str, site_name: str) -> List[Match]:
        html = self.get(url)
        if not html:
            return []

        soup = self.soup(html)
        matches = []
        seen = set()

        containers = soup.select(",".join(MATCH_SELECTORS)) or soup.find_all(["div", "article", "tr", "li"],
                                                                              class_=re.compile(r"match|game|event|live|fixture", re.I))

        if not containers:
            containers = soup.find_all(["div", "li", "tr"], limit=50)

        for container in containers[:30]:
            title = self._extract_text(container, TITLE_SELECTORS)
            if not title or len(title) < 5:
                continue

            link = self._extract_link(container, url)
            league = self._extract_text(container, LEAGUE_SELECTORS)
            match_time = self._extract_text(container, TIME_SELECTORS)
            channels = [c.get_text(strip=True) for c in
                        sum((container.select(s) for s in CHANNEL_SELECTORS), [])
                        if c.get_text(strip=True)]
            status = self._detect_generic_status(container)

            streams = []
            if link:
                detail = self.get(link)
                if detail:
                    streams = self.extract_links(detail)

            home_team, away_team = self.extract_teams(title)
            mid = self.make_id(title, link or url)
            if mid in seen:
                continue
            seen.add(mid)

            match = Match(
                id=mid, title=title,
                home_team=home_team, away_team=away_team,
                league=league, match_time=match_time,
                match_date=datetime.now().strftime("%Y-%m-%d"),
                status=status,
                channels=list(set(channels)),
                streams=streams,
                source=f"generic_{site_name}",
                source_url=link or url,
            )
            matches.append(match)

        return matches

    def _scrape_rss(self, feed_url: str, site_name: str) -> List[Match]:
        html = self.get(feed_url)
        if not html:
            return []

        matches = []
        seen = set()
        try:
            soup = self.soup(html)
            for item in soup.select("item"):
                title_el = item.select_one("title")
                title = title_el.get_text(strip=True) if title_el else None
                link_el = item.select_one("link")
                link = link_el.get_text(strip=True) if link_el else None
                desc_el = item.select_one("description")
                desc = desc_el.get_text(strip=True) if desc_el else ""

                if not title or len(title) < 5:
                    continue
                if not self._is_football(title + " " + desc):
                    continue

                home_team, away_team = self.extract_teams(title)
                mid = self.make_id(title, link or feed_url)
                if mid in seen:
                    continue
                seen.add(mid)

                match = Match(
                    id=mid, title=title,
                    home_team=home_team, away_team=away_team,
                    match_date=datetime.now().strftime("%Y-%m-%d"),
                    status="scheduled",
                    source=f"rss_{site_name}",
                    source_url=link or feed_url,
                )
                matches.append(match)
        except Exception:
            pass

        return matches

    def _scrape_telegram(self, url: str, site_name: str) -> List[Match]:
        html = self.get(url)
        if not html:
            return []

        soup = self.soup(html)
        matches = []
        seen = set()

        for msg in soup.select(".tgme_widget_message_wrap, .tgme_widget_message, .message"):
            text = msg.get_text(strip=True)
            if not self._is_football(text):
                continue

            links = msg.select("a[href]")
            first_link = None
            for a in links:
                href = a.get("href", "")
                if href.startswith("http") and "t.me" not in href:
                    first_link = href
                    break

            home_team, away_team = self.extract_teams(text)
            mid = self.make_id(text[:50], first_link or url)
            if mid in seen:
                continue
            seen.add(mid)

            match = Match(
                id=mid, title=text[:100],
                home_team=home_team, away_team=away_team,
                match_date=datetime.now().strftime("%Y-%m-%d"),
                status="live" if any(w in text.lower() for w in ["live", "مباشر", "الآن"]) else "scheduled",
                streams=[StreamLink(url=first_link, source=f"tg_{site_name}")] if first_link else [],
                source=f"tg_{site_name}",
                source_url=first_link or url,
            )
            matches.append(match)

        return matches

    def _scrape_iptv(self, url: str, site_name: str) -> List[Match]:
        html = self.get(url)
        if not html:
            return []

        matches = []
        seen = set()

        m3u8_links = re.findall(r'(https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*)', html)
        for link in m3u8_links:
            title = "IPTV Channel"
            mid = self.make_id(link, link)
            if mid in seen:
                continue
            seen.add(mid)

            match = Match(
                id=mid, title=title,
                match_date=datetime.now().strftime("%Y-%m-%d"),
                status="live",
                streams=[StreamLink(url=link, source=f"iptv_{site_name}", is_verified=True)],
                source=f"iptv_{site_name}",
                source_url=link,
            )
            matches.append(match)

        return matches

    def _extract_text(self, container, selectors: List[str]) -> Optional[str]:
        for sel in selectors:
            el = container.select_one(sel)
            if el:
                if el.name == "a" and el.get("title"):
                    return el["title"]
                return el.get_text(strip=True)[:150]
        return None

    def _extract_link(self, container, base_url: str) -> Optional[str]:
        for sel in LINK_SELECTORS:
            el = container.select_one(sel)
            if el:
                href = el.get("href", "")
                return href if href.startswith("http") else urljoin(base_url, href)
        el = container.select_one("a[href]")
        if el:
            href = el.get("href", "")
            if href.startswith("http") or href.startswith("/"):
                return href if href.startswith("http") else urljoin(base_url, href)
        return None

    def _detect_generic_status(self, container) -> str:
        for sel in STATUS_SELECTORS:
            el = container.select_one(sel)
            if el:
                t = el.get_text(strip=True).lower()
                if "live" in t or "مباشر" in t or "now" in t:
                    return "live"
                if "انتهى" in t or "final" in t or "ended" in t:
                    return "finished"
        text = container.get_text().lower()
        if "live" in text or "مباشر" in text or "now" in text:
            return "live"
        return "scheduled"

    def _is_football(self, text: str) -> bool:
        keywords = [
            "كرة", "football", "soccer", "مباراة", "match", "الدوري",
            "champions", "league", "كأس", "cup", " UEFA ", " FIFA ",
            "الاهلي", "الهلال", "النصر", "الاتحاد", "الزمالك", "برشلونة",
            "ريال", "مدريد", "بايرن", "ليفربول", "مانشستر", "تشيلسي",
            "ارسنال", "توتنهام", "يوفنتوس", "ميلان", "انتر", "باريس",
            "psg", "juventus", "liverpool", "manchester", "barcelona",
            "real madrid", "bayern", "chelsea", "arsenal", "tottenham",
            "دوري ابطال", "دوري أبطال", "دوري اوروبا", "دوري أوروبا",
            "تصفيات", "qualifiers", "world cup", "كأس العالم", "مونديال",
            "المنتخب", "national team", "ودية", "friendly",
            "المكسيك", "انجلترا", "البرتغال", "بوليفيا", "النمسا",
            "نيجيريا", "كوستاريكا", "غواتيمالا",
        ]
        t = text.lower()
        return any(kw in t for kw in keywords)
