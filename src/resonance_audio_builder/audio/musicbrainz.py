"""
MusicBrainz API client for fetching composer and credits information.
Uses ISRC to lookup recording details.

Rate limited to 1 request per second per MusicBrainz API requirements.
"""

import threading
import time
from typing import Optional

import requests

# Global rate limiter - MusicBrainz allows 1 request/second
_rate_lock = threading.Lock()
_last_request_time = 0.0
_MIN_INTERVAL = 1.1  # Slightly over 1 second to be safe


def _rate_limited_get(url: str, headers: dict, timeout: int = 5):
    """Make a rate-limited GET request to MusicBrainz"""
    global _last_request_time

    with _rate_lock:
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _last_request_time = time.time()

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


def _get_recording_id(isrc: str, headers: dict) -> Optional[str]:
    """Search by ISRC and return the first recording ID"""
    url = f"https://musicbrainz.org/ws/2/recording?query=isrc:{isrc}&fmt=json"
    resp = _rate_limited_get(url, headers=headers, timeout=5)

    if resp.status_code != 200:
        return None

    data = resp.json()
    recordings = data.get("recordings", [])

    if not recordings:
        return None

    return recordings[0].get("id")


def _extract_credits_from_details(detail: dict, headers: dict) -> dict:
    """Extract credits from recording detail JSON"""
    composers = []
    producers = []
    engineers = []

    # Extract from artist relations
    for rel in detail.get("relations", []):
        rel_type = rel.get("type", "").lower()
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

    # Also check work relations for composers
    for work_rel in detail.get("relations", []):
        if work_rel.get("type") == "performance":
            work = work_rel.get("work", {})
            work_id = work.get("id")
            if work_id:
                work_composers = _fetch_work_composers(work_id, headers)
                composers.extend(work_composers)

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
