import time
from pathlib import Path

import requests
from mutagen.id3 import APIC, COMM, ID3, TALB, TIT2, TPE1, TPE2, TPOS, TRCK, TSRC, TYER, USLT
from mutagen.mp3 import MP3

from resonance_audio_builder.audio.lyrics import fetch_lyrics
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.core.logger import Logger


class MetadataWriter:
    def __init__(self, logger: Logger):
        self.log = logger

    def write(self, path: Path, meta: TrackMetadata):
        """Escribe tags ID3 y carátula"""
        if not path.exists():
            return

        try:
            # Cargar o crear tags
            try:
                audio = MP3(str(path), ID3=ID3)
            except Exception:
                audio = MP3(str(path))

            if audio.tags is None:
                audio.add_tags()

            # Tags de texto (encoding=3 = UTF-16)
            def add_tag(tag_class, value):
                if value:
                    try:
                        audio.tags.add(tag_class(encoding=3, text=str(value)))
                    except Exception as e:
                        self.log.debug(f"Error adding tag {tag_class.__name__}: {e}")

            self.log.debug(f"Writing metadata for {meta.title}...")

            add_tag(TIT2, meta.title)
            add_tag(TPE1, meta.artist)
            add_tag(TALB, meta.album)
            add_tag(TPE2, meta.album_artist)

            if meta.release_date and len(meta.release_date) >= 4:
                add_tag(TYER, meta.release_date[:4])

            add_tag(TRCK, meta.track_number)
            add_tag(TPOS, meta.disc_number)
            add_tag(TSRC, meta.isrc)

            if meta.spotify_uri:
                audio.tags.add(COMM(encoding=3, lang="eng", desc="", text=f"Spotify: {meta.spotify_uri}"))

            # Caratula
            if meta.cover_url:
                try:
                    resp = requests.get(meta.cover_url, timeout=10)
                    if resp.status_code == 200 and len(resp.content) > 0:
                        audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=resp.content))
                except Exception as e:
                    self.log.debug(f"Error descargando caratula: {e}")

            # Letras (USLT tag)
            try:
                lyrics = fetch_lyrics(meta.artist, meta.title, meta.duration_seconds)
                if lyrics:
                    audio.tags.add(USLT(encoding=3, lang="eng", desc="", text=lyrics))
                    self.log.debug(f"Letras embebidas para: {meta.title}")
            except Exception as e:
                self.log.debug(f"Error obteniendo letras: {e}")

            # Guardar como ID3v2.3 (mejor compatibilidad)
            # Reintentar guardar si hay bloqueo de archivo
            max_retries = 3
            for i in range(max_retries):
                try:
                    audio.save(v2_version=3)
                    break
                except Exception as save_err:
                    if i == max_retries - 1:
                        raise save_err
                    time.sleep(0.5)

        except Exception as e:
            self.log.error(f"FATAL METADATA ERROR: {e}")
            print(f"\n[!] Error saving tags for {meta.title}: {e}")
