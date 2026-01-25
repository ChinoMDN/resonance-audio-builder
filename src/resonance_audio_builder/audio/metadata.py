from dataclasses import dataclass, field
import hashlib

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
    raw_data: dict = field(default_factory=dict)

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

        isrc = get_val("isrc", "code")
        artist = get_val("artist name(s)", "artist", "artist name")
        title = get_val("track name", "track", "title", "name")

        if isrc:
            track_id = f"isrc_{isrc}"
        else:
            track_id = hashlib.md5(f"{artist}_{title}".encode()).hexdigest()[:16]

        duration_str = get_val("track duration (ms)", "duration_ms", "duration")
        duration = int(duration_str) if duration_str and duration_str.isdigit() else 0

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
        )

    @property
    def duration_seconds(self) -> int:
        return self.duration_ms // 1000 if self.duration_ms else 0

    @property
    def safe_filename(self) -> str:
        name = f"{self.artist} - {self.title}"
        # Include ; for security, and other common shell chars
        invalids = '<>:"/\\|?*;$#&()![]{}'
        for char in invalids:
            name = name.replace(char, "")
        
        # Sequentially collapse any sequences of dots that could form ..
        while ".." in name:
            name = name.replace("..", ".")
            
        name = name.strip().rstrip(".")
        return name[:150]
