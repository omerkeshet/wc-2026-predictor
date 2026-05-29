"""
api-football.com v3 client with on-disk caching and quota tracking.

Free tier is 100 requests/day. The cache makes that go a *long* way for
this use case — fixtures don't change minute-to-minute, and team rosters
are essentially static for a tournament.

Set API_FOOTBALL_KEY in the environment.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import requests


BASE_URL = "https://v3.football.api-sports.io"
WC_LEAGUE_ID = 1  # FIFA World Cup
DEFAULT_CACHE_DIR = Path(".cache/api_football")
QUOTA_FILE = Path(".cache/api_football/_quota.json")


@dataclass
class ApiFootballClient:
    api_key: str
    cache_dir: Path = DEFAULT_CACHE_DIR
    cache_ttl_hours: int = 6  # most endpoints
    request_delay_sec: float = 0.4  # be polite

    def __post_init__(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ---- quota tracking ------------------------------------------------

    def _load_quota(self) -> Dict[str, Any]:
        if not QUOTA_FILE.exists():
            return {"date": str(date.today()), "count": 0}
        try:
            with open(QUOTA_FILE) as f:
                q = json.load(f)
            if q.get("date") != str(date.today()):
                return {"date": str(date.today()), "count": 0}
            return q
        except (json.JSONDecodeError, OSError):
            return {"date": str(date.today()), "count": 0}

    def _bump_quota(self) -> None:
        q = self._load_quota()
        q["count"] += 1
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(QUOTA_FILE, "w") as f:
            json.dump(q, f)

    def quota_used_today(self) -> int:
        return self._load_quota()["count"]

    # ---- cache --------------------------------------------------------

    def _cache_path(self, endpoint: str, params: Dict[str, Any]) -> Path:
        key = endpoint + "?" + json.dumps(params, sort_keys=True)
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        safe = endpoint.replace("/", "_")
        return self.cache_dir / f"{safe}_{h}.json"

    def _read_cache(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > self.cache_ttl_hours * 3600:
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _write_cache(self, path: Path, data: Dict[str, Any]) -> None:
        with open(path, "w") as f:
            json.dump(data, f)

    # ---- HTTP ---------------------------------------------------------

    def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """GET an endpoint with caching. Returns the JSON response dict."""
        params = params or {}
        cache_path = self._cache_path(endpoint, params)

        if not force_refresh:
            cached = self._read_cache(cache_path)
            if cached is not None:
                return cached

        # Make a real request
        time.sleep(self.request_delay_sec)
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        headers = {"x-apisports-key": self.api_key}
        resp = requests.get(url, headers=headers, params=params, timeout=20)

        self._bump_quota()  # count every real request, even errors

        resp.raise_for_status()
        data = resp.json()

        # Surface api-football's own error envelope
        errors = data.get("errors")
        if errors and (isinstance(errors, dict) and errors or isinstance(errors, list) and errors):
            raise RuntimeError(f"api-football error: {errors}")

        self._write_cache(cache_path, data)
        return data

    # ---- typed helpers ------------------------------------------------

    def fixtures(
        self,
        *,
        league: int = WC_LEAGUE_ID,
        season: Optional[int] = None,
        team: Optional[int] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """List fixtures. Filter by league/season/team/date range."""
        params: Dict[str, Any] = {"league": league}
        if season:
            params["season"] = season
        if team:
            params["team"] = team
        if from_date:
            params["from"] = from_date.isoformat()
        if to_date:
            params["to"] = to_date.isoformat()
        if status:
            params["status"] = status
        return self.get("fixtures", params).get("response", [])

    def standings(self, league: int = WC_LEAGUE_ID, season: Optional[int] = None) -> list[dict]:
        params: Dict[str, Any] = {"league": league}
        if season:
            params["season"] = season
        return self.get("standings", params).get("response", [])

    def injuries(self, team_id: int, season: int) -> list[dict]:
        return self.get("injuries", {"team": team_id, "season": season}).get("response", [])

    def teams(self, league: int = WC_LEAGUE_ID, season: Optional[int] = None) -> list[dict]:
        params: Dict[str, Any] = {"league": league}
        if season:
            params["season"] = season
        return self.get("teams", params).get("response", [])


def from_env() -> ApiFootballClient:
    return ApiFootballClient(api_key="e0e63f6c5d4b9e1eb49ccd3a728fa014")
