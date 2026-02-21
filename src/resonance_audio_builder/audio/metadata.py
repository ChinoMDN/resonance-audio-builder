import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional


def _get_value(r_norm: dict, *keys) -> str:
    """Look up a value from a normalized dict by trying multiple keys."""
    for k in keys:
        val = r_norm.get(k.lower())
        if val is not None:
            return val.strip()
    return ""


def _get_float(r_norm: dict, *keys) -> float:
    """Look up a float value from a normalized dict."""
    try:
        val = _get_value(r_norm, *keys)
        return float(val) if val else 0.0
    except ValueError:
        return 0.0


def _get_int(r_norm: dict, *keys) -> int:
    """Look up an int value from a normalized dict."""
    try:
        val = _get_value(r_norm, *keys)
        return int(float(val)) if val else 0
    except ValueError:
        return 0


@dataclass
class TrackMetadata:
    track_id: str
    title: str
    artist: str
    album: str = ""
    album_artist: str = ""
    release_date: str = ""
    track_number: str = ""
    disc_number: str = ""
    isrc: str = ""
    spotify_uri: str = ""
    cover_url: str = ""
    duration_ms: int = 0
    cover_data: Optional[bytes] = None
    raw_data: dict = field(default_factory=dict)

    # Metadatos extendidos
    genres: str = ""
    album_genres: str = ""
    popularity: int = 0
    explicit: bool = False
    label: str = ""
    copyrights: str = ""
    preview_url: str = ""
    added_by: str = ""
    added_at: str = ""

    # MusicBrainz fields
    composers: List[str] = field(default_factory=list)
    producers: List[str] = field(default_factory=list)
    engineers: List[str] = field(default_factory=list)

    # Audio features
    tempo: float = 0.0
    energy: float = 0.0
    danceability: float = 0.0
    valence: float = 0.0  # Musical positiveness
    acousticness: float = 0.0
    instrumentalness: float = 0.0
    speechiness: float = 0.0
    liveness: float = 0.0
    loudness: float = 0.0
    key: int = 0
    mode: int = 0  # 0 = minor, 1 = major
    time_signature: int = 4

    @property
    def artists(self) -> List[str]:
        r"""
        Spotify exporta colaboraciones separadas por comas:
        - "Wisin & Yandel" = UN artista (dúo)
        - "Wisin & Yandel, Romeo Santos" = DOS artistas (colaboración)
        - "Daniel\, Me Estás Matando" = UN artista (nombre con coma)
        """
        if not self.artist:
            return []

        # Usar Regex para separar solo si la coma NO está escapada
        # (?<!\\), significa: "una coma que no tenga una barra invertida antes"
        parts = re.split(r"(?<!\\),", self.artist)

        # Limpiar cada parte y reemplazar comas escapadas por comas normales
        cleaned_artists = []
        for p in parts:
            name = p.strip().replace("\\,", ",")
            if name:
                cleaned_artists.append(name)

        return cleaned_artists if cleaned_artists else [self.artist]

    @property
    def genre_list(self) -> List[str]:
        """Returns list of genres from the genres string"""
        if not self.genres:
            return []
        return [g.strip() for g in self.genres.split(",") if g.strip()]

    @classmethod
    def from_csv_row(cls, row: dict) -> "TrackMetadata":
        # Normalizar claves a minúsculas y quitar espacios
        r_norm = {k.strip().lower(): v for k, v in row.items()}
        r_orig = {k.strip(): v for k, v in row.items()}

        gv = lambda *k: _get_value(r_norm, *k)  # noqa: E731
        gf = lambda *k: _get_float(r_norm, *k)  # noqa: E731
        gi = lambda *k: _get_int(r_norm, *k)  # noqa: E731

        isrc = gv("isrc", "code")
        artist = gv("artist name(s)", "artist", "artist name")
        title = gv("track name", "track", "title", "name")

        if isrc:
            tid = f"isrc_{isrc}"
        else:
            tid = hashlib.md5(f"{artist}_{title}".encode(), usedforsecurity=False).hexdigest()[:16]

        return cls(
            track_id=tid,
            artist=artist,
            title=title,
            isrc=isrc,
            album=gv("album name", "album"),
            album_artist=gv("album artist name(s)", "album artist"),
            release_date=gv("album release date", "release date", "date", "year"),
            track_number=gv("track number", "track no"),
            disc_number=gv("disc number", "disc no"),
            duration_ms=gi("track duration (ms)", "duration ms", "duration", "ms"),
            spotify_uri=gv("track uri", "spotify uri", "uri"),
            cover_url=gv("album image url", "image url", "cover"),
            raw_data=r_orig,
            popularity=gi("popularity"),
            explicit=gv("explicit").lower() in ("true", "1", "yes"),
            genres=gv("artist genres", "genres", "genre"),
            album_genres=gv("album genres"),
            label=gv("label", "publisher"),
            copyrights=gv("copyrights", "copyright"),
            preview_url=gv("track preview url", "preview url"),
            added_by=gv("added by"),
            added_at=gv("added at"),
            tempo=gf("tempo", "bpm"),
            energy=gf("energy"),
            danceability=gf("danceability"),
            valence=gf("valence"),
            acousticness=gf("acousticness"),
            instrumentalness=gf("instrumentalness"),
            liveness=gf("liveness"),
            speechiness=gf("speechiness"),
            loudness=gf("loudness"),
            key=gi("key"),
            mode=gi("mode"),
            time_signature=gi("time signature", "time_signature") or 4,
        )

    @property
    def duration_seconds(self) -> int:
        return self.duration_ms // 1000 if self.duration_ms else 0

    @property
    def safe_filename(self) -> str:
        name = f"{self.artist} - {self.title}"

        # 1. Reemplazo inteligente de barras por guiones (AC/DC -> AC-DC)
        name = name.replace("/", "-").replace("\\", "-")

        # 2. Caracteres prohibidos en Windows y Shell
        # (pero permitimos parentesis y corchetes)
        # Prohibidos: < > : " | ? * y también ; $ # & ! { }
        # (peligrosos en shell)
        invalids = '<>:"|?*;$#&!{}'
        for char in invalids:
            name = name.replace(char, "")

        # 3. Limpieza de secuencias peligrosas
        # Evitar .. para path traversal
        while ".." in name:
            name = name.replace("..", ".")

        name = name.strip().rstrip(".")
        return name[:150]
