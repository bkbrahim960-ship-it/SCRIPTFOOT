import os
import sqlite3
import json
import threading
from datetime import datetime
from typing import List, Optional, Dict
from models import Match, StreamLink
from config import config


class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.database_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS matches (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    home_team TEXT,
                    away_team TEXT,
                    league TEXT,
                    stadium TEXT,
                    status TEXT DEFAULT 'scheduled',
                    score TEXT,
                    match_time TEXT,
                    match_date TEXT,
                    channels TEXT DEFAULT '[]',
                    streams TEXT DEFAULT '[]',
                    source TEXT NOT NULL,
                    source_url TEXT,
                    thumbnail TEXT,
                    updated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
                CREATE INDEX IF NOT EXISTS idx_matches_source ON matches(source);
                CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date);
            """)

    def save_match(self, match: Match) -> bool:
        match.home_team_info = None
        match.away_team_info = None
        with self._lock:
            try:
                with self._get_connection() as conn:
                    existing = conn.execute(
                        "SELECT streams, channels, created_at FROM matches WHERE id = ?",
                        (match.id,)
                    ).fetchone()

                    if existing:
                        existing_streams = json.loads(existing["streams"])
                        existing_channels = json.loads(existing["channels"])

                        new_urls = {s.url for s in match.streams}
                        old_urls = {s["url"] for s in existing_streams}
                        if new_urls.issubset(old_urls) and match.status == existing["status"]:
                            return False

                        merged_streams = {s["url"]: s for s in existing_streams}
                        for s in match.streams:
                            if s.url not in merged_streams:
                                merged_streams[s.url] = s.model_dump()
                            elif s.is_verified and not merged_streams[s.url].get("is_verified"):
                                merged_streams[s.url]["is_verified"] = True

                        merged_channels = list(set(existing_channels + match.channels))
                        match.created_at = existing["created_at"]
                    else:
                        merged_streams = {s.url: s.model_dump() for s in match.streams}
                        merged_channels = match.channels

                    match.updated_at = datetime.utcnow().isoformat()
                    match.streams = []
                    match.channels = []

                    conn.execute("""
                        INSERT OR REPLACE INTO matches
                        (id, title, home_team, away_team, league, stadium,
                         status, score, match_time, match_date,
                         channels, streams, source, source_url,
                         thumbnail, updated_at, created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        match.id, match.title, match.home_team, match.away_team,
                        match.league, match.stadium, match.status, match.score,
                        match.match_time, match.match_date,
                        json.dumps(merged_channels, ensure_ascii=False),
                        json.dumps(list(merged_streams.values()), ensure_ascii=False),
                        match.source, match.source_url, match.thumbnail,
                        match.updated_at, match.created_at
                    ))
                    return True
            except Exception as e:
                print(f"[DB] Error saving match {match.id}: {e}")
                return False

    def get_all_matches(self, status: Optional[str] = None, source: Optional[str] = None, league: Optional[str] = None) -> List[Match]:
        query = "SELECT * FROM matches WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if source:
            query += " AND source = ?"
            params.append(source)
        if league:
            query += " AND league LIKE ?"
            params.append(f"%{league}%")
        query += " ORDER BY match_date DESC, match_time ASC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        results = []
        for row in rows:
            match_dict = dict(row)
            match_dict["channels"] = json.loads(match_dict.get("channels", "[]"))
            match_dict["streams"] = [StreamLink(**s) for s in json.loads(match_dict.get("streams", "[]"))]
            results.append(Match(**match_dict))
        return results

    def get_match(self, match_id: str) -> Optional[Match]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM matches WHERE id = ?", (match_id,)
            ).fetchone()
        if not row:
            return None
        match_dict = dict(row)
        match_dict["channels"] = json.loads(match_dict.get("channels", "[]"))
        match_dict["streams"] = [StreamLink(**s) for s in json.loads(match_dict.get("streams", "[]"))]
        return Match(**match_dict)

    def get_live_matches(self) -> List[Match]:
        return self.get_all_matches(status="live")

    def get_matches_count(self) -> int:
        with self._get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]

    def get_live_count(self) -> int:
        with self._get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM matches WHERE status='live'").fetchone()[0]

    def get_sources(self) -> List[str]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT DISTINCT source FROM matches").fetchall()
        return [r["source"] for r in rows]

    def get_last_update_time(self) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT updated_at FROM matches ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return row["updated_at"] if row else None

    def clear_old_matches(self, days: int = 1):
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM matches WHERE date(created_at) < date('now', ?)",
                (f"-{days} days",)
            )
            conn.execute("VACUUM")


db = Database()
