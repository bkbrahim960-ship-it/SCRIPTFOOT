import os
from dataclasses import dataclass, field
from typing import List

@dataclass
class Config:
    database_path: str = os.getenv("DATABASE_PATH", "data/matches.db")
    update_interval_seconds: int = int(os.getenv("UPDATE_INTERVAL", "60"))

    server_host: str = os.getenv("HOST", "0.0.0.0")
    server_port: int = int(os.getenv("PORT", "8000"))

    enable_yalla_shoot: bool = True
    enable_yalla_koora: bool = True
    enable_goalhi: bool = True
    enable_kora_online: bool = True
    enable_bein_match: bool = True
    enable_akwam: bool = True
    enable_mashahd: bool = True
    enable_threesat: bool = True
    enable_link_resolver: bool = True
    enable_playwright: bool = True

    yalla_shoot_urls: List[str] = field(default_factory=lambda: [
        "https://www.yallashoot.io",
        "https://yallashoot.name",
    ])
    yalla_koora_urls: List[str] = field(default_factory=lambda: [
        "https://www.yallakoora.com",
    ])
    goalhi_url: str = "https://goalhi.com"
    kora_online_url: str = "https://www.kora-online.com"
    bein_match_url: str = "https://bein-match.com"

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    request_timeout: int = 15

    api_title: str = "ScriptMatch API"
    api_description: str = "API لجلب المباريات وروابط البث المباشر"
    api_version: str = "1.0.0"

    cors_origins: List[str] = field(default_factory=lambda: ["*"])

config = Config()
