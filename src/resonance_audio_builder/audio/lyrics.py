import requests
from typing import Optional

def fetch_lyrics(artist: str, title: str, duration_sec: int = 0) -> Optional[str]:
    """
    Busca letras de canciones en APIs gratuitas.
    Intenta primero LRCLIB (letras sincronizadas), luego lyrics.ovh.
    """
    # Limpiar caracteres especiales
    clean_artist = artist.split(",")[0].strip()  # Solo primer artista
    clean_title = title.split("(")[0].split("-")[0].strip()  # Sin remixes/versions

    # 1. Intentar LRCLIB (letras sincronizadas .lrc)
    try:
        url = "https://lrclib.net/api/get"
        params = {
            "artist_name": clean_artist,
            "track_name": clean_title,
        }
        if duration_sec > 0:
            params["duration"] = duration_sec

        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            # Preferir letras sincronizadas, sino las normales
            lyrics = data.get("syncedLyrics") or data.get("plainLyrics")
            if lyrics and len(lyrics) > 50:
                return lyrics
    except:
        pass

    # 2. Fallback a lyrics.ovh (API gratuita)
    try:
        url = f"https://api.lyrics.ovh/v1/{clean_artist}/{clean_title}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            lyrics = data.get("lyrics", "")
            if lyrics and len(lyrics) > 50:
                return lyrics.strip()
    except:
        pass

    return None
