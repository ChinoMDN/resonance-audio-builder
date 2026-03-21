"""
MusicBrainz API client for fetching composer and credits information.
Uses ISRC to lookup recording details.

Rate limited to 1 request per second per MusicBrainz API requirements.
"""

import threading
import time
from typing import Optional

import requests

_MIN_INTERVAL = 1.1  # Slightly over 1 second to be safe
_MIN_RECORDING_SCORE = 85


class _RateLimiter:
    """Simple per-process limiter for MusicBrainz requests."""

    def __init__(self, min_interval: float):
        self._lock = threading.Lock()
        self._last_request_time = 0.0
        self._min_interval = min_interval

    def wait_turn(self):
        with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_request_time = time.time()


_rate_limiter = _RateLimiter(_MIN_INTERVAL)


def _rate_limited_get(url: str, headers: dict, timeout: int = 5):
    """Make a rate-limited GET request to MusicBrainz"""
    _rate_limiter.wait_turn()

    return requests.get(url, headers=headers, timeout=timeout)


def fetch_credits(isrc: str) -> dict:
    """
    Busca créditos de una canción en MusicBrainz usando el ISRC.

    Returns dict with:
        - composers: List of composer/writer names
        - producers: List of producer names
        - engineers: List of engineer names
    """
    if not isrc:
        return {}

    try:
        headers = {
            "User-Agent": ("ResonanceAudioBuilder/1.0 (https://github.com/resonance)"),
            "Accept": "application/json",
        }

        recording_id = _get_recording_id(isrc, headers)
        if not recording_id:
            return {}

        detail_url = f"https://musicbrainz.org/ws/2/recording/{recording_id}" "?inc=artist-rels+work-rels&fmt=json"
        detail_resp = _rate_limited_get(detail_url, headers=headers, timeout=5)

        if detail_resp.status_code != 200:
            return {}

        detail = detail_resp.json()
        return _extract_credits_from_details(detail, headers)

    except Exception:
        return {}


def _score_recordings(recordings: list[dict]) -> Optional[str]:
    """Extract and score recordings by confidence, returning best or first unscored."""
    scored = []
    unscored = []

    for rec in recordings:
        rec_id = rec.get("id")
        if not rec_id:
            continue

        score_raw = rec.get("score")
        if score_raw is None:
            unscored.append(rec_id)
            continue

        try:
            score = int(score_raw)
            if score >= _MIN_RECORDING_SCORE:
                scored.append((score, rec_id))
        except (TypeError, ValueError):
            continue

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    return unscored[0] if unscored else None


def _get_recording_id(isrc: str, headers: dict) -> Optional[str]:
    """Search by ISRC and return the first recording ID"""
    url = f"https://musicbrainz.org/ws/2/recording?query=isrc:{isrc}&fmt=json"
    resp = _rate_limited_get(url, headers=headers, timeout=5)

    if resp.status_code != 200:
        return None

    data = resp.json()
    recordings = data.get("recordings", [])
    return _score_recordings(recordings) if recordings else None


def _extract_credits_from_details(detail: dict, headers: dict) -> dict:
    """Extract credits from recording detail JSON"""
    composers = []
    producers = []
    engineers = []
    work_ids = []

    for rel in detail.get("relations", []):
        rel_type = rel.get("type", "").lower()

        if rel_type == "performance":
            work_id = rel.get("work", {}).get("id")
            if work_id:
                work_ids.append(work_id)

        artist = rel.get("artist", {})
        name = artist.get("name", "")

        if not name:
            continue

        if rel_type in ("composer", "writer", "lyricist"):
            composers.append(name)
        elif rel_type == "producer":
            producers.append(name)
        elif rel_type in ("engineer", "mix", "mastering"):
            engineers.append(name)

    if work_ids:
        unique_work_ids = list(dict.fromkeys(work_ids))
        # MusicBrainz is strictly rate-limited (1 req/s), so deterministic
        # sequential calls are safer than thread fan-out here.
        for work_id in unique_work_ids:
            composers.extend(_fetch_work_composers(work_id, headers))

    return {
        "composers": list(dict.fromkeys(composers)),
        "producers": list(dict.fromkeys(producers)),
        "engineers": list(dict.fromkeys(engineers)),
    }


def _fetch_work_composers(work_id: str, headers: dict) -> list:
    """Fetch composers from a work entity"""
    try:
        url = f"https://musicbrainz.org/ws/2/work/{work_id}" "?inc=artist-rels&fmt=json"
        resp = _rate_limited_get(url, headers=headers, timeout=5)

        if resp.status_code != 200:
            return []

        data = resp.json()
        composers = []

        for rel in data.get("relations", []):
            rel_type = rel.get("type", "").lower()
            artist = rel.get("artist", {})
            name = artist.get("name", "")

            if name and rel_type in ("composer", "writer", "lyricist"):
                composers.append(name)

        return composers
    except Exception:
        return []


def get_composer_string(isrc: str) -> Optional[str]:
    """
    Convenience function that returns composers as a comma-separated string.
    Returns None if no composers found.
    """
    mb_credits = fetch_credits(isrc)
    composers = mb_credits.get("composers", [])

    if composers:
        return ", ".join(composers)
    return None
