import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional


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

    # New extended metadata fields
    genres: str = ""  # Artist genres (comma-separated)
    album_genres: str = ""  # Album genres
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
        Parsea el campo artist y devuelve una lista de artistas individuales.
        Maneja comas escapadas (ej: "Daniel\, Me Estás Matando") correctamente.

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
        r_norm = {k.strip().lower(): v for k, v in row.items()}
        r_original = {k.strip(): v for k, v in row.items()}

        def get_val(*keys):
            for k in keys:
                val = r_norm.get(k.lower())
                if val is not None:
                    return val.strip()
            return ""

        def get_float(*keys):
            val = get_val(*keys)
            try:
                return float(val) if val else 0.0
            except ValueError:
                return 0.0

        def get_int(*keys):
            val = get_val(*keys)
            try:
                return int(float(val)) if val else 0
            except ValueError:
                return 0

        isrc = get_val("isrc", "code")
        artist = get_val("artist name(s)", "artist", "artist name")
        title = get_val("track name", "track", "title", "name")

        if isrc:
            track_id = f"isrc_{isrc}"
        else:
            # Fallback robusto: MD5 de Artist + Title
            track_id = hashlib.md5(f"{artist}_{title}".encode(), usedforsecurity=False).hexdigest()[:16]

        duration_str = get_val("track duration (ms)", "duration_ms", "duration")
        duration = int(duration_str) if duration_str and duration_str.isdigit() else 0

        # Parse explicit field
        explicit_str = get_val("explicit").lower()
        explicit = explicit_str in ("true", "1", "yes")

        return cls(
            track_id=track_id,
            title=title,
            artist=artist,
            album=get_val("album name", "album"),
            album_artist=get_val("album artist name(s)", "album artist"),
            release_date=get_val("album release date", "release date", "year"),
            track_number=get_val("track number", "track no"),
            disc_number=get_val("disc number", "disc no"),
            isrc=isrc,
            spotify_uri=get_val("track uri", "uri", "spotify uri"),
            cover_url=get_val("album image url", "image url", "cover"),
            duration_ms=duration,
            raw_data=r_original,
            # Extended metadata
            genres=get_val("artist genres", "genres", "genre"),
            album_genres=get_val("album genres"),
            popularity=get_int("popularity"),
            explicit=explicit,
            label=get_val("label"),
            copyrights=get_val("copyrights"),
            preview_url=get_val("track preview url", "preview url"),
            added_by=get_val("added by"),
            added_at=get_val("added at"),
            # Audio features
            tempo=get_float("tempo", "bpm"),
            energy=get_float("energy"),
            danceability=get_float("danceability"),
            valence=get_float("valence"),
            acousticness=get_float("acousticness"),
            instrumentalness=get_float("instrumentalness"),
            speechiness=get_float("speechiness"),
            liveness=get_float("liveness"),
            loudness=get_float("loudness"),
            key=get_int("key"),
            mode=get_int("mode"),
            time_signature=get_int("time signature", "time_signature") or 4,
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
