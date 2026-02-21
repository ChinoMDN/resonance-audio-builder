import time
from pathlib import Path

from mutagen.mp4 import MP4, MP4Cover

from resonance_audio_builder.audio.lyrics import fetch_lyrics
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.audio.musicbrainz import fetch_credits
from resonance_audio_builder.core.logger import Logger


class MetadataWriter:
    """Writes M4A metadata tags using Mutagen."""

    def __init__(self, logger: Logger):
        self.log = logger

    def write(self, path: Path, meta: TrackMetadata):
        """Escribe metadatos M4A (AAC)"""
        if not path.exists():
            return

        # Enriquecer con datos externos (MusicBrainz)
        self._enrich_metadata(meta)

        # Mecanismo de reintento por si el archivo está bloqueado por Windows
        # o Antivirus
        max_retries = 3
        for i in range(max_retries):
            try:
                self._write_m4a_tags(path, meta)
                break
            except Exception as e:
                if i == max_retries - 1:
                    self.log.error(f"FATAL METADATA ERROR ({path.name}): {e}")
                time.sleep(0.5)

    def _enrich_metadata(self, meta: TrackMetadata):
        """Enriquece los metadatos con MusicBrainz si está disponible"""
        # Solo buscar si tenemos ISRC y no tenemos ya los datos
        # (para evitar re-fetch si se llama varias veces)
        if not meta.isrc or (meta.composers or meta.producers):
            return

        try:
            mb_credits = fetch_credits(meta.isrc)
            if mb_credits:
                meta.composers = mb_credits.get("composers", [])
                meta.producers = mb_credits.get("producers", [])
                meta.engineers = mb_credits.get("engineers", [])
                if meta.composers:
                    self.log.debug(f"Fetched MusicBrainz credits for {meta.title}")
        except Exception as e:
            self.log.debug(f"Failed to fetch MusicBrainz credits: {e}")

    def _write_m4a_tags(self, path: Path, meta: TrackMetadata):
        try:
            audio = MP4(path)
        except Exception:
            # If failing to open, maybe it's corrupted or locked.
            # Try passing simply path string
            audio = MP4(str(path))

        self._write_m4a_basic_tags(audio, meta)
        self._write_m4a_numbers(audio, meta)

        # --- 3. Letras (Lyrics) ---
        try:
            lyrics = fetch_lyrics(meta.artist, meta.title, meta.duration_seconds)
            if lyrics:
                audio["\xa9lyr"] = lyrics
                self.log.debug(f"Lyrics embedded for: {meta.title}")
        except Exception:
            pass

        # --- 4. Carátula (Cover Art) - CRÍTICO EN M4A ---
        if meta.cover_data:
            self._embed_cover_m4a(audio, meta.cover_data)

        self._write_m4a_extended_tags(audio, meta)
        audio.save()

    def _write_m4a_basic_tags(self, audio, meta: TrackMetadata):
        self._write_m4a_text_tags(audio, meta)
        self._write_m4a_copyright_tags(audio, meta)
        self._write_m4a_tool_tags(audio, meta)

    def _write_m4a_text_tags(self, audio, meta: TrackMetadata):
        """Write core text tags: title, artist, album, date, genre."""
        if meta.title:
            audio["\xa9nam"] = meta.title
        if meta.artists:
            audio["\xa9ART"] = meta.artists
        if meta.album:
            audio["\xa9alb"] = meta.album
        if meta.album_artist:
            audio["aART"] = meta.album_artist
        if meta.release_date and len(meta.release_date) >= 4:
            audio["\xa9day"] = meta.release_date[:4]  # Año
        if meta.genres:
            main_genre = meta.genre_list[0] if meta.genre_list else meta.genres.split(",")[0]
            audio["\xa9gen"] = main_genre

    def _write_m4a_copyright_tags(self, audio, meta: TrackMetadata):
        """Write copyright and publisher tags."""
        if meta.copyrights:
            audio["cprt"] = meta.copyrights
        elif meta.label:
            audio["cprt"] = meta.label

        if meta.label:
            try:
                audio["\xa9pub"] = meta.label
            except Exception:
                pass

    def _write_m4a_tool_tags(self, audio, meta: TrackMetadata):
        """Write encoder, comment, and tempo tags."""
        audio["\xa9too"] = "Resonance Audio Builder"
        try:
            audio["\xa9enc"] = "Resonance Audio Builder"
        except Exception:
            pass

        if meta.spotify_uri:
            audio["\xa9cmt"] = f"Spotify: {meta.spotify_uri}"  # Comentario

        if meta.tempo and meta.tempo > 0:
            audio["tmpo"] = [int(meta.tempo)]

    def _write_m4a_numbers(self, audio, meta: TrackMetadata):
        # --- 2. Números (Tuplas) ---
        if meta.track_number:
            try:
                tn = int(meta.track_number)
                audio["trkn"] = [(tn, 0)]
            except ValueError:
                pass

        if meta.disc_number:
            try:
                dn = int(meta.disc_number)
                audio["disk"] = [(dn, 0)]
            except ValueError:
                pass

    def _write_m4a_extended_tags(self, audio, meta: TrackMetadata):
        # --- 5. Extended Metadata & Freeform Atoms ---
        if meta.composers:
            audio["\xa9wrt"] = ", ".join(meta.composers)

        if meta.explicit:
            audio["rtng"] = [4 if meta.explicit else 2]

        # Helper para freeform tags (----:com.apple.iTunes:NAME)
        def set_freeform(name: str, value):
            if value:
                key = f"----:com.apple.iTunes:{name}"
                val_bytes = str(value).encode("utf-8")
                audio[key] = [val_bytes]

        set_freeform("ISRC", meta.isrc)
        set_freeform("SPOTIFY_POPULARITY", meta.popularity)
        set_freeform("ADDED_BY", meta.added_by)
        set_freeform("ADDED_AT", meta.added_at)
        set_freeform("LABEL", meta.label)
        set_freeform("COPYRIGHT", meta.copyrights)

        if meta.release_date:
            set_freeform("ORIGINAL_YEAR", meta.release_date[:4])

        # Audio Features
        set_freeform("ENERGY", meta.energy)
        set_freeform("DANCEABILITY", meta.danceability)
        set_freeform("VALENCE", meta.valence)
        set_freeform("ACOUSTICNESS", meta.acousticness)
        set_freeform("INSTRUMENTALNESS", meta.instrumentalness)
        set_freeform("LIVENESS", meta.liveness)
        set_freeform("SPEECHINESS", meta.speechiness)
        set_freeform("LOUDNESS", meta.loudness)
        set_freeform("KEY", meta.key)
        set_freeform("MODE", meta.mode)
        set_freeform("TIME_SIGNATURE", meta.time_signature)

        # MusicBrainz Credits
        if meta.producers:
            set_freeform("PRODUCER", ", ".join(meta.producers))
        if meta.engineers:
            set_freeform("ENGINEER", ", ".join(meta.engineers))

    def _embed_cover_m4a(self, audio, data: bytes):
        """
        M4A es estricto: Debes decirle si es JPEG o PNG.
        MP3 no le importaba, pero M4A mostrará carátula vacía si te equivocas.
        """
        try:
            # Detectar formato por "Magic Bytes"
            if data.startswith(b"\xff\xd8\xff"):
                fmt = MP4Cover.FORMAT_JPEG
            elif data.startswith(b"\x89PNG"):
                fmt = MP4Cover.FORMAT_PNG
            else:
                # Si no es ni JPG ni PNG, mejor no poner nada para no corromper
                return

            audio["covr"] = [MP4Cover(data, imageformat=fmt)]
        except Exception as e:
            self.log.debug(f"Error embedding cover: {e}")
