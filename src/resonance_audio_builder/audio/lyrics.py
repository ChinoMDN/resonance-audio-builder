import re
from typing import Optional

import requests

LRCLIB_HEADERS = {
    "User-Agent": "ResonanceAudioBuilder/1.0 (https://github.com/resonance)",
}


def _clean_artist(artist: str) -> str:
    """Solo el primer artista listado."""
    return artist.split(",")[0].split("&")[0].split(" ft.")[0].strip()


def _clean_title(title: str) -> str:
    """Elimina sufijos de versión pero preserva guiones dentro de palabras."""
    # Remover paréntesis y su contenido: "(Radio Edit)", "(feat. X)", etc.
    title = re.sub(r"\s*\(.*?\)", "", title)
    # Remover sufijos después de " - " (espacio-guion-espacio), no guiones mid-word
    title = re.sub(r"\s+-\s+.*$", "", title)
    return title.strip()


def _extract_lyrics(payload: dict) -> tuple[Optional[str], str]:
    synced = payload.get("syncedLyrics")
    if synced:
        return synced, "synced"

    plain = payload.get("plainLyrics")
    if plain:
        return plain, "plain"

    return None, "none"


def _fetch_lrclib(artist: str, title: str, album: str = "", duration_sec: int = 0) -> tuple[Optional[str], str]:
    """
    Try LRCLIB endpoints in descending precision:
    1) /api/get-cached
    2) /api/get
    3) /api/search
    """
    # Exact signature endpoints require all fields.
    if artist and title and album and duration_sec > 0:
        params: dict[str, str | int] = {
            "artist_name": artist,
            "track_name": title,
            "album_name": album,
            "duration": duration_sec,
        }

        try:
            resp = requests.get(
                "https://lrclib.net/api/get-cached",
                params=params,
                timeout=5,
                headers=LRCLIB_HEADERS,
            )
            if resp.status_code == 200:
                lyrics, lyrics_type = _extract_lyrics(resp.json())
                if lyrics:
                    return lyrics, lyrics_type
        except Exception:
            pass

        try:
            resp = requests.get(
                "https://lrclib.net/api/get",
                params=params,
                timeout=10,
                headers=LRCLIB_HEADERS,
            )
            if resp.status_code == 200:
                lyrics, lyrics_type = _extract_lyrics(resp.json())
                if lyrics:
                    return lyrics, lyrics_type
        except Exception:
            pass

    try:
        resp = requests.get(
            "https://lrclib.net/api/search",
            params={
                "track_name": title,
                "artist_name": artist,
                "album_name": album,
            },
            timeout=5,
            headers=LRCLIB_HEADERS,
        )
        if resp.status_code == 200:
            results = resp.json()
            if isinstance(results, dict):
                lyrics, lyrics_type = _extract_lyrics(results)
                if lyrics:
                    return lyrics, lyrics_type
            elif results:
                lyrics, lyrics_type = _extract_lyrics(results[0])
                if lyrics:
                    return lyrics, lyrics_type
    except Exception:
        pass

    return None, "none"


def _fetch_genius(artist: str, title: str) -> Optional[str]:
    """Optional fallback to Genius via lyricsgenius (lazy import)."""
    try:
        import lyricsgenius

        genius = lyricsgenius.Genius(
            timeout=8,
            retries=1,
            verbose=False,
            remove_section_headers=True,
        )
        song = genius.search_song(title, artist)
        if song and song.lyrics:
            return re.sub(r"\d*Embed$", "", song.lyrics).strip()
    except Exception:
        pass
    return None


def fetch_lyrics_with_info(
    artist: str,
    title: str,
    album: str = "",
    duration_sec: int = 0,
) -> tuple[Optional[str], str]:
    """Return lyrics and type: synced, plain, or none."""
    # Backward compatibility: historical signature was
    # fetch_lyrics(artist, title, duration_sec).
    if isinstance(album, int) and duration_sec == 0:
        duration_sec = album
        album = ""

    clean_artist = _clean_artist(artist)
    clean_title = _clean_title(title)
    clean_album = _clean_title(album) if album else ""

    lyrics, lyrics_type = _fetch_lrclib(clean_artist, clean_title, clean_album, duration_sec)
    if lyrics:
        return lyrics, lyrics_type

    lyrics = _fetch_genius(clean_artist, clean_title)
    if lyrics:
        return lyrics, "plain"

    return None, "none"


def fetch_lyrics(artist: str, title: str, album: str = "", duration_sec: int = 0) -> Optional[str]:
    """
    Fetch lyrics prioritizing LRCLIB and optionally falling back to Genius.
    """
    lyrics, _ = fetch_lyrics_with_info(artist, title, album, duration_sec)
    return lyrics
