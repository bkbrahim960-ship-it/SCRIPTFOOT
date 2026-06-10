from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class StreamLink(BaseModel):
    url: str
    quality: Optional[str] = None
    channel: Optional[str] = None
    source: str
    is_verified: bool = False


class Team(BaseModel):
    name: str
    name_en: Optional[str] = None
    logo: Optional[str] = None


class Match(BaseModel):
    id: str
    title: str
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    home_team_info: Optional[Team] = None
    away_team_info: Optional[Team] = None
    league: Optional[str] = None
    league_logo: Optional[str] = None
    stadium: Optional[str] = None
    status: str = "scheduled"
    score: Optional[str] = None
    match_time: Optional[str] = None
    match_date: Optional[str] = None
    channels: List[str] = Field(default_factory=list)
    streams: List[StreamLink] = Field(default_factory=list)
    source: str
    source_url: str
    thumbnail: Optional[str] = None
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class MatchResponse(BaseModel):
    success: bool
    data: List[Match]
    total: int
    source: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SingleMatchResponse(BaseModel):
    success: bool
    data: Optional[Match] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class HealthResponse(BaseModel):
    status: str
    matches_count: int
    live_count: int
    sources_active: List[str]
    last_update: Optional[str] = None
    uptime: float
