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

        def get_v(*keys):
            for k in keys:
                val = r_norm.get(k.lower())
                if val is not None:
                    return val.strip()
            return ""

        def get_f(*keys):
            try:
                val = get_v(*keys)
                return float(val) if val else 0.0
            except ValueError:
                return 0.0

        def get_i(*keys):
            try:
                val = get_v(*keys)
                return int(float(val)) if val else 0
            except ValueError:
                return 0

        isrc = get_v("isrc", "code")
        artist = get_v("artist name(s)", "artist", "artist name")
        title = get_v("track name", "track", "title", "name")

        if isrc:
            tid = f"isrc_{isrc}"
        else:
            tid = hashlib.md5(f"{artist}_{title}".encode(), usedforsecurity=False).hexdigest()[:16]

        return cls(
            track_id=tid,
            artist=artist,
            title=title,
            isrc=isrc,
            album=get_v("album name", "album"),
            album_artist=get_v("album artist name(s)", "album artist"),
            release_date=get_v("album release date", "release date", "date", "year"),
            track_number=get_v("track number", "track no"),
            disc_number=get_v("disc number", "disc no"),
            duration_ms=get_i("track duration (ms)", "duration ms", "duration", "ms"),
            spotify_uri=get_v("track uri", "spotify uri", "uri"),
            cover_url=get_v("album image url", "image url", "cover"),
            raw_data=r_orig,
            popularity=get_i("popularity"),
            explicit=get_v("explicit").lower() in ("true", "1", "yes"),
            genres=get_v("artist genres", "genres", "genre"),
            album_genres=get_v("album genres"),
            label=get_v("label", "publisher"),
            copyrights=get_v("copyrights", "copyright"),
            preview_url=get_v("track preview url", "preview url"),
            added_by=get_v("added by"),
            added_at=get_v("added at"),
            tempo=get_f("tempo", "bpm"),
            energy=get_f("energy"),
            danceability=get_f("danceability"),
            valence=get_f("valence"),
            acousticness=get_f("acousticness"),
            instrumentalness=get_f("instrumentalness"),
            liveness=get_f("liveness"),
            speechiness=get_f("speechiness"),
            loudness=get_f("loudness"),
            key=get_i("key"),
            mode=get_i("mode"),
            time_signature=get_i("time signature", "time_signature") or 4,
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
