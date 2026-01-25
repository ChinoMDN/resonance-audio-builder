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

    def _add_text_tags(self, audio, meta: TrackMetadata):
        """Aplica etiquetas de texto básicas"""
        tags = {
            TIT2: meta.title,
            TPE1: meta.artist,
            TALB: meta.album,
            TPE2: meta.album_artist,
            TRCK: meta.track_number,
            TPOS: meta.disc_number,
            TSRC: meta.isrc,
        }

        for tag_class, value in tags.items():
            if value:
                try:
                    audio.tags.add(tag_class(encoding=3, text=str(value)))
                except Exception as e:
                    self.log.debug(f"Error adding tag {tag_class.__name__}: {e}")

        if meta.release_date and len(meta.release_date) >= 4:
            audio.tags.add(TYER(encoding=3, text=meta.release_date[:4]))

        if meta.spotify_uri:
            audio.tags.add(COMM(encoding=3, lang="eng", desc="", text=f"Spotify: {meta.spotify_uri}"))

    def _add_cover(self, audio, meta: TrackMetadata):
        """Descarga y aplica la carátula"""
        if meta.cover_url:
            try:
                resp = requests.get(meta.cover_url, timeout=10)
                if resp.status_code == 200 and len(resp.content) > 0:
                    audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=resp.content))
            except Exception as e:
                self.log.debug(f"Error descargando caratula: {e}")

    def _add_lyrics(self, audio, meta: TrackMetadata):
        """Busca y aplica las letras"""
        try:
            lyrics = fetch_lyrics(meta.artist, meta.title, meta.duration_seconds)
            if lyrics:
                audio.tags.add(USLT(encoding=3, lang="eng", desc="", text=lyrics))
                self.log.debug(f"Letras embebidas para: {meta.title}")
        except Exception as e:
            self.log.debug(f"Error obteniendo letras: {e}")

    def write(self, path: Path, meta: TrackMetadata):
        """Escribe todos los metadatos en el archivo"""
        if not path.exists():
            return

        try:
            audio = self._load_audio(path)
            if audio.tags is None:
                audio.add_tags()

            self.log.debug(f"Writing metadata for {meta.title}...")
            self._add_text_tags(audio, meta)
            self._add_cover(audio, meta)
            self._add_lyrics(audio, meta)

            self._save_audio(audio, meta)

        except Exception as e:
            self.log.error(f"FATAL METADATA ERROR: {e}")
            print(f"\n[!] Error saving tags for {meta.title}: {e}")

    def _load_audio(self, path: Path) -> MP3:
        try:
            return MP3(str(path), ID3=ID3)
        except Exception:
            return MP3(str(path))

    def _save_audio(self, audio: MP3, meta: TrackMetadata):
        max_retries = 3
        for i in range(max_retries):
            try:
                audio.save(v2_version=3)
                break
            except Exception as save_err:
                if i == max_retries - 1:
                    raise save_err
                time.sleep(0.5)
