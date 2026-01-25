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

    def download(self, search_result: SearchResult, track: TrackMetadata, check_quit=None, subfolder: str = "") -> DownloadResult:
        """
        Descarga, convierte y etiqueta una canción.
        Retorna DownloadResult.
        """
        raw_path = None
        try:
            # 1. Determinar rutas de salida
            hq_folder = Path(self.cfg.OUTPUT_FOLDER_HQ)
            mobile_folder = Path(self.cfg.OUTPUT_FOLDER_MOBILE)
            
            if subfolder:
                hq_folder = hq_folder / subfolder
                mobile_folder = mobile_folder / subfolder
            
            quality_mode = self.cfg.MODE
            needed_hq = quality_mode in [QualityMode.HQ_ONLY, QualityMode.BOTH]
            needed_mobile = quality_mode in [QualityMode.MOBILE_ONLY, QualityMode.BOTH]

            if needed_hq:
                hq_folder.mkdir(parents=True, exist_ok=True)
            if needed_mobile:
                mobile_folder.mkdir(parents=True, exist_ok=True)

            filename = f"{track.safe_filename}.mp3"
            hq_path = hq_folder / filename
            mobile_path = mobile_folder / filename

            # 2. Verificar existencia (Skip si ya existe en la calidad solicitada)
            hq_exists = hq_path.exists() and hq_path.stat().st_size > 0
            mobile_exists = mobile_path.exists() and mobile_path.stat().st_size > 0

            todo_hq = needed_hq and not hq_exists
            todo_mob = needed_mobile and not mobile_exists

            if not todo_hq and not todo_mob:
                return DownloadResult(True, 0, skipped=True)

            # 3. Obtener URL de descarga e iniciar descarga RAW
            url = search_result.url if search_result else None
            if not url:
                url = f"ytsearch1:{track.artist} - {track.title} audio"
            
            self.log.info(f"Downloading: {track.title}")
            raw_path = self._download_raw(url, track.track_id)

            if not raw_path or not raw_path.exists():
                return DownloadResult(False, 0, "Download failed (no file)")

            if check_quit and check_quit():
                return DownloadResult(False, 0, "Cancelled", skipped=True)

            # 4. Análisis Espectral (Anti-Fake HQ)
            fake_hq = False
            if self.cfg.SPECTRAL_ANALYSIS and todo_hq:
                is_hq = self.analyzer.analyze_integrity(raw_path, cutoff_hz=self.cfg.SPECTRAL_CUTOFF)
                if not is_hq:
                    self.log.warning(f"Fake HQ detected for {track.title}")
                    fake_hq = True

            total_bytes = 0
            success = True

            # 5. Transcodificar HQ
            if todo_hq:
                self.log.debug(f"Transcoding HQ ({self.cfg.QUALITY_HQ_BITRATE}k)...")
                if self._transcode(raw_path, hq_path, self.cfg.QUALITY_HQ_BITRATE):
                    self._inject_metadata(hq_path, track)
                    total_bytes += hq_path.stat().st_size
                else:
                    success = False

            if check_quit and check_quit():
                return DownloadResult(False, 0, "Cancelled", skipped=True)

            # 6. Transcodificar Mobile
            if todo_mob:
                self.log.debug(f"Transcoding Mobile ({self.cfg.QUALITY_MOBILE_BITRATE}k)...")
                if self._transcode(raw_path, mobile_path, self.cfg.QUALITY_MOBILE_BITRATE):
                    self._inject_metadata(mobile_path, track)
                    total_bytes += mobile_path.stat().st_size
                else:
                    success = False

            if success:
                return DownloadResult(True, total_bytes, fake_hq=fake_hq)
            else:
                return DownloadResult(False, 0, "Transcode failed")

        except Exception as e:
            self.log.error(f"Download error {track.title}: {e}")
            return DownloadResult(False, 0, f"Error: {str(e)}")
        
        finally:
            # 7. Limpieza
            if raw_path and raw_path.exists():
                try:
                    os.remove(raw_path)
                except:
                    pass

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
            "fragment_retries": 10,  # Increase fragment retries
            "skip_unavailable_fragments": True,
            "geo_bypass": True,
            "http_headers": {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-us,en;q=0.5",
                "Sec-Fetch-Mode": "navigate",
            },
            # Common fix for 403 Forbidden
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"],
                    "po_token": ["web+web_embedded_player"],
                }
            },
        }
        
        if self.cfg.DEBUG_MODE:
            opts["quiet"] = False
            opts["no_warnings"] = False
            opts["verbose"] = True

        if self.proxy_manager:
            proxy = self.proxy_manager.get_proxy()
            if proxy:
                opts["proxy"] = proxy
                # self.log.debug(f"Using proxy for download: {proxy}")

        if self._cookies_valid:
            opts["cookiefile"] = self.cfg.COOKIES_FILE

        # Force logging to file to inspect later
        class FileLogger:
            def debug(self, msg):
                with open("ytdlp_raw.log", "a", encoding="utf-8") as f:
                    f.write(f"[DEBUG] {msg}\n")
            def warning(self, msg):
                with open("ytdlp_raw.log", "a", encoding="utf-8") as f:
                    f.write(f"[WARNING] {msg}\n")
            def error(self, msg):
                with open("ytdlp_raw.log", "a", encoding="utf-8") as f:
                    f.write(f"[ERROR] {msg}\n")
        
        opts["logger"] = FileLogger()

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise NotFoundError("yt-dlp no retornó información")
                
                final_path = Path(ydl.prepare_filename(info))
                
                if not final_path.exists():
                    # Debug: List what IS there
                    try:
                        files = list(temp_dir.glob("*"))
                        self.log.debug(f"MISSING: {final_path}")
                        self.log.debug(f"FOUND in {temp_dir}: {[f.name for f in files]}")
                        
                        # Emergency fallback: if there's only one file that overlaps in name, grab it
                        # Or if prepare_filename predicted wrong extension
                        stem = final_path.stem
                        for f in files:
                            if f.stem == stem:
                                self.log.debug(f"Recovered file with different ext: {f}")
                                return f
                    except:
                        pass
                
                return final_path

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
                raise RecoverableError(f"Error descarga: {str(e)}")

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
