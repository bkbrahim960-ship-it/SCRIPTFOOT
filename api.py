import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import config
from database import db
from models import MatchResponse, SingleMatchResponse, HealthResponse, Match, Team
from updater import Updater
from team_data import find_team, find_teams_in_text, get_team_logo

app = FastAPI(
    title=config.api_title,
    description=config.api_description,
    version=config.api_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

updater = Updater()
_start_time = time.time()


def enrich_match(match: Match) -> Match:
    if not match.home_team and not match.away_team:
        teams = find_teams_in_text(match.title)
        if len(teams) >= 2:
            match.home_team = teams[0]["ar"]
            match.away_team = teams[1]["ar"]
            match.home_team_info = Team(name=teams[0]["ar"], name_en=teams[0].get("en"), logo=teams[0].get("logo"))
            match.away_team_info = Team(name=teams[1]["ar"], name_en=teams[1].get("en"), logo=teams[1].get("logo"))
        elif len(teams) == 1:
            match.home_team = teams[0]["ar"]
            match.home_team_info = Team(name=teams[0]["ar"], name_en=teams[0].get("en"), logo=teams[0].get("logo"))
    if match.home_team and not match.home_team_info:
        info = find_team(match.home_team)
        if info:
            match.home_team = info["ar"]
            match.home_team_info = Team(name=info["ar"], name_en=info.get("en"), logo=info.get("logo"))
        else:
            match.home_team_info = Team(name=match.home_team, logo=get_team_logo(match.home_team))
    if match.away_team and not match.away_team_info:
        info = find_team(match.away_team)
        if info:
            match.away_team = info["ar"]
            match.away_team_info = Team(name=info["ar"], name_en=info.get("en"), logo=info.get("logo"))
        else:
            match.away_team_info = Team(name=match.away_team, logo=get_team_logo(match.away_team))
    if not match.home_team_info or not match.away_team_info:
        teams = find_teams_in_text(match.title)
        for t in teams:
            if not match.home_team_info:
                match.home_team = t["ar"]
                match.home_team_info = Team(name=t["ar"], name_en=t.get("en"), logo=t.get("logo"))
            elif not match.away_team_info and t.get("key") != (match.home_team_info.name if match.home_team_info else None):
                match.away_team = t["ar"]
                match.away_team_info = Team(name=t["ar"], name_en=t.get("en"), logo=t.get("logo"))
    if match.home_team and not match.home_team_info:
        match.home_team_info = Team(name=match.home_team, logo=get_team_logo(match.home_team))
    if match.away_team and not match.away_team_info:
        match.away_team_info = Team(name=match.away_team, logo=get_team_logo(match.away_team))
    match.status_ar = compute_status_ar(match)
    return match


def compute_status_ar(match: Match) -> str:
    if match.status == "live":
        return "مباشر الآن"
    if match.status == "finished":
        return "انتهت"
    now = datetime.now()
    try:
        if match.match_date:
            parts = match.match_date.split("-")
            if len(parts) == 3:
                md = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
                today = now.replace(hour=0, minute=0, second=0)
                if md < today:
                    return "انتهت"
                diff = (md - today).days
                if diff == 0:
                    return "اليوم"
                if diff == 1:
                    return "غداً"
                if diff == 2:
                    return "بعد غد"
                return f"بعد {diff} أيام"
    except Exception:
        pass
    return "لم تبدأ"


@app.on_event("startup")
async def startup():
    db.cleanup_junk()
    updater.start()


@app.on_event("shutdown")
async def shutdown():
    updater.stop()


@app.get("/api/matches", response_model=MatchResponse)
def get_matches(
    status: Optional[str] = Query(None, description="filter: live, scheduled, finished"),
    source: Optional[str] = Query(None, description="source name filter"),
    league: Optional[str] = Query(None, description="league name filter"),
):
    matches = db.get_all_matches(status=status, source=source, league=league)
    matches = [enrich_match(m) for m in matches]
    return MatchResponse(
        success=True,
        data=matches,
        total=len(matches),
    )


@app.get("/api/matches/live", response_model=MatchResponse)
def get_live_matches():
    matches = db.get_live_matches()
    matches = [enrich_match(m) for m in matches]
    return MatchResponse(
        success=True,
        data=matches,
        total=len(matches),
    )


@app.get("/api/matches/{match_id}", response_model=SingleMatchResponse)
def get_match(match_id: str):
    match = db.get_match(match_id)
    if not match:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Match not found", "timestamp": datetime.utcnow().isoformat()}
        )
    match = enrich_match(match)
    return SingleMatchResponse(success=True, data=match)


@app.get("/api/sources")
def get_sources():
    return {
        "success": True,
        "data": db.get_sources(),
        "total_active": len(updater.active_sources),
        "active_sources": updater.active_sources,
    }


@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        matches_count=db.get_matches_count(),
        live_count=db.get_live_count(),
        sources_active=updater.active_sources,
        last_update=db.get_last_update_time(),
        uptime=round(time.time() - _start_time, 2),
    )


@app.get("/")
def root():
    return {
        "app": config.api_title,
        "version": config.api_version,
        "docs": "/docs",
        "endpoints": {
            "matches": "/api/matches",
            "live": "/api/matches/live",
            "sources": "/api/sources",
            "health": "/api/health",
        }
    }
