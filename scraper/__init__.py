from scraper.yalla_shoot import YallaShootScraper
from scraper.yalla_koora import YallaKooraScraper
from scraper.goalhi import GoalHIScraper
from scraper.kora_online import KoraOnlineScraper
from scraper.bein_match import BeinMatchScraper
from scraper.akwam import AkwamScraper
from scraper.mashahd import MashahdScraper
from scraper.threesat import ThreeSatScraper
from scraper.generic_scraper import GenericScraper
from scraper.base import BaseScraper

SCRAPERS: list[type[BaseScraper]] = [
    YallaShootScraper,
    YallaKooraScraper,
    GoalHIScraper,
    KoraOnlineScraper,
    BeinMatchScraper,
    AkwamScraper,
    MashahdScraper,
    ThreeSatScraper,
    GenericScraper,
]
