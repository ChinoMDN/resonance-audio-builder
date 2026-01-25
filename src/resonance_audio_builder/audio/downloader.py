import os
import random
import time
import subprocess
import tempfile
import requests
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yt_dlp
from mutagen.id3 import APIC, COMM, ID3, TALB, TIT2, TPE1, TPE2, TPOS, TRCK, TSRC, TYER
from mutagen.mp3 import MP3

from resonance_audio_builder.core.config import Config, QualityMode
from resonance_audio_builder.core.logger import Logger
from resonance_audio_builder.core.exceptions import (
    RecoverableError, FatalError, TranscodeError, CopyrightError, GeoBlockError, NotFoundError
)
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.audio.youtube import SearchResult
from resonance_audio_builder.audio.analysis import AudioAnalyzer
from resonance_audio_builder.network.utils import USER_AGENTS, validate_cookies_file
from resonance_audio_builder.network.proxies import ProxyManager

@dataclass
class DownloadResult:
    success: bool
    bytes: int
    error: str = None
    skipped: bool = False
    fake_hq: bool = False

class AudioDownloader:
    def __init__(self, config: Config, logger: Logger, proxy_manager: ProxyManager = None):
        self.cfg = config
        self.log = logger
        self._cookies_valid = validate_cookies_file(config.COOKIES_FILE)
        self.analyzer = AudioAnalyzer(logger)
        self.proxy_manager = proxy_manager

    # download method unchanged

    def _download_cover(self, url: str) -> Optional[bytes]:
        """Descarga imagen de portada del álbum"""
        if not url or len(url) < 10:
            return None

        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            proxies = self.proxy_manager.get_requests_proxies() if self.proxy_manager else {}
            
            response = requests.get(url, timeout=10, headers=headers, proxies=proxies)
            if response.status_code == 200:
                return response.content
        except Exception as e:
            self.log.debug(f"Error descargando cover: {e}")
        return None
    
    # _inject_metadata method unchanged until _download_raw
    def _inject_metadata(self, file_path: Path, track: TrackMetadata) -> bool:
        """Inyecta metadatos ID3 al archivo MP3"""
        try:
            # Crear/cargar tags ID3
            try:
                audio = MP3(str(file_path), ID3=ID3)
            except Exception:
                audio = MP3(str(file_path))

            # Eliminar tags existentes
            try:
                audio.delete()
            except Exception:
                pass

            # Recargar y crear tags nuevos
            audio = MP3(str(file_path))
            audio.add_tags()

            # Metadatos básicos
            if track.title:
                audio.tags.add(TIT2(encoding=3, text=track.title))
            if track.artist:
                audio.tags.add(TPE1(encoding=3, text=track.artist))
            if track.album:
                audio.tags.add(TALB(encoding=3, text=track.album))
            if track.album_artist:
                audio.tags.add(TPE2(encoding=3, text=track.album_artist))

            # Año (extraer de release_date)
            if track.release_date and len(track.release_date) >= 4:
                audio.tags.add(TYER(encoding=3, text=track.release_date[:4]))

            # Número de pista y disco
            if track.track_number:
                audio.tags.add(TRCK(encoding=3, text=track.track_number))
            if track.disc_number:
                audio.tags.add(TPOS(encoding=3, text=track.disc_number))

            # ISRC
            if track.isrc:
                audio.tags.add(TSRC(encoding=3, text=track.isrc))

            # Comentario con URI de Spotify
            if track.spotify_uri:
                audio.tags.add(COMM(encoding=3, lang="eng", desc="", text=f"Spotify: {track.spotify_uri}"))

            # Carátula del álbum
            if track.cover_url:
                cover_data = self._download_cover(track.cover_url)
                if cover_data:
                    audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_data))
                    self.log.debug("Cover art embebido")

            audio.save(v2_version=3)
            self.log.debug(f"Metadatos inyectados: {track.title}")
            return True

        except Exception as e:
            self.log.debug(f"Error inyectando metadatos: {e}")
            return False

    def _download_raw(self, url: str, name: str) -> Path:
        """Descarga audio raw de YouTube"""
        temp_dir = Path(tempfile.gettempdir())
        out_tmpl = temp_dir / f"ytraw_{name}_{int(time.time())}.%(ext)s"

        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(out_tmpl),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "socket_timeout": 15,
            "retries": 3,
            "fragment_retries": 3,
            "skip_unavailable_fragments": True,
            "http_headers": {"User-Agent": random.choice(USER_AGENTS)},
        }

        if self.proxy_manager:
            proxy = self.proxy_manager.get_proxy()
            if proxy:
                opts["proxy"] = proxy
                # self.log.debug(f"Using proxy for download: {proxy}")

        if self._cookies_valid:
            opts["cookiefile"] = self.cfg.COOKIES_FILE

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise NotFoundError("yt-dlp no retornó información")
                return Path(ydl.prepare_filename(info))

        except yt_dlp.utils.DownloadError as e:
            error_str = str(e).lower()

            # Detectar HTTP 429
            if "429" in error_str or "too many requests" in error_str:
                self.log.warning("YouTube Rate Limit detected (HTTP 429). Pausing for 60s...")
                time.sleep(60)
                raise RecoverableError("Rate Limit (429) - Retrying after pause")

            if "copyright" in error_str or "blocked" in error_str:
                raise CopyrightError(f"Bloqueado: {str(e)[:50]}")
            elif "not available" in error_str or "geo" in error_str:
                raise GeoBlockError(f"No disponible en tu región")
            elif "sign in" in error_str or "age" in error_str:
                raise FatalError(f"Requiere login: {str(e)[:50]}")
            else:
                raise RecoverableError(f"Error descarga: {str(e)[:50]}")

    def _transcode(self, input_path: Path, output_path: Path, bitrate: str) -> bool:
        """
        Transcodifica audio a MP3 con normalizacion EBU R128 opcional.
        """
        # Construir comando base
        cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(input_path),
            "-vn",
        ]

        # Agregar normalizacion EBU R128 si esta habilitada
        # loudnorm: I=-14 (loudness target), TP=-1.5 (true peak), LRA=11 (loudness range)
        if self.cfg.NORMALIZE_AUDIO:
            cmd.extend(["-filter:a", "loudnorm=I=-14:TP=-1.5:LRA=11"])

        # Parametros de codificacion MP3
        cmd.extend(
            [
                "-acodec",
                "libmp3lame",
                "-b:a",
                f"{bitrate}k",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-map_metadata",
                "-1",
                str(output_path),
            ]
        )

        try:
            # Aumentar timeout a 5 minutos y no checkear error code inmediatamente
            # ya que ffmpeg puede emitir warnings no fatales
            result = subprocess.run(
                cmd, timeout=300, check=False, capture_output=True, creationflags=0x08000000 if os.name == "nt" else 0
            )

            # Verificar existencia del archivo y tamaño > 0
            if output_path.exists() and output_path.stat().st_size > 0:  # Check size > 0 only
                return True

            # Si falló, loggear stderr (solo si no existe el archivo)
            err_msg = result.stderr.decode(errors="ignore") if result.stderr else "Unknown error"
            self.log.debug(f"FFmpeg falló (RC={result.returncode}): {err_msg[:200]}")

            # Limpiar archivo corrupto/vacio
            if output_path.exists():
                try:
                    os.remove(output_path)
                except:
                    pass

            return False

        except subprocess.TimeoutExpired:
            self.log.debug("Timeout en FFmpeg (300s)")
            if output_path.exists():
                try:
                    os.remove(output_path)
                except:
                    pass
            return False

        except Exception as e:
            self.log.debug(f"Error transcodificacion: {e}")
            if output_path.exists():
                try:
                    os.remove(output_path)
                except:
                    pass
            return False
