#!/usr/bin/env python3
"""
ScriptMatch - Professional Football Match Scraper & API
=======================================================
يجلب المباريات وروابط البث المباشر من عدة مواقع عربية
ويوفر REST API لربطه بموقعك أو تطبيقك

Usage:
    python main.py              # تشغيل API السيرفر
    python main.py --scrape     # تشغيل سكراب مرة واحدة فقط
    python main.py --update     # تشغيل التحديث المستمر بدون API
"""

import sys
import argparse

import uvicorn

from config import config
from scraper import SCRAPERS
from database import db


def run_scrape_once():
    total = 0
    for scraper_cls in SCRAPERS:
        scraper = scraper_cls()
        if not scraper.enabled:
            continue
        try:
            matches = scraper.scrape()
            for match in matches:
                db.save_match(match)
            total += len(matches)
        finally:
            scraper.cleanup()
    print(f"\nDone. Total matches: {total}")


def run_updater():
    from updater import Updater
    updater = Updater()
    updater.start()
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        updater.stop()


def run_server():
    uvicorn.run(
        "api:app",
        host=config.server_host,
        port=config.server_port,
        log_level="info",
    )


def main():
    parser = argparse.ArgumentParser(
        description="ScriptMatch - Football Match Scraper & API"
    )
    parser.add_argument(
        "--scrape", action="store_true",
        help="تشغيل سكراب لمرة واحدة وجلب كل المباريات"
    )
    parser.add_argument(
        "--update", action="store_true",
        help="تشغيل التحديث المستمر بدون API"
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="منفذ السيرفر (default: 8000)"
    )

    args = parser.parse_args()

    if args.port:
        config.server_port = args.port

    if args.scrape:
        run_scrape_once()
    elif args.update:
        run_updater()
    else:
        run_server()


if __name__ == "__main__":
    main()
