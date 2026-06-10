import time
import threading
from datetime import datetime
from typing import List

from config import config
from database import db
from scraper import SCRAPERS
from scraper.base import BaseScraper


class Updater:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._running = False
        self.active_sources: List[str] = []
        self._last_update: str | None = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[Updater] Started (interval: {config.update_interval_seconds}s)")

    def stop(self):
        self._running = False
        print("[Updater] Stopped")

    def _loop(self):
        while self._running:
            try:
                self._run_once()
            except Exception as e:
                print(f"[Updater] Error in update cycle: {e}")
            time.sleep(config.update_interval_seconds)

    def _run_once(self):
        self.active_sources = []
        total_new = 0
        total_matches = 0

        for scraper_cls in SCRAPERS:
            scraper: BaseScraper = scraper_cls()
            if not scraper.enabled:
                continue
            try:
                print(f"[Updater] Scraping {scraper.name}...")
                matches = scraper.scrape()
                saved = 0
                for match in matches:
                    if db.save_match(match):
                        saved += 1
                total_new += saved
                total_matches += len(matches)
                self.active_sources.append(scraper.name)
                print(f"[Updater] {scraper.name}: {len(matches)} matches, {saved} new")
            except Exception as e:
                print(f"[Updater] {scraper.name} failed: {e}")
            finally:
                scraper.cleanup()

        self._last_update = datetime.utcnow().isoformat()
        print(
            f"[Updater] Done. "
            f"Sources: {len(self.active_sources)}, "
            f"Matches: {total_matches}, "
            f"New/Updated: {total_new}"
        )

    def force_update(self):
        self._run_once()
