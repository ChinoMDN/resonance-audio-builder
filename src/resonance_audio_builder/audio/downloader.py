import asyncio
import io
import json
import os
import random
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, Optional, Tuple

import aiohttp
import yt_dlp
from mutagen.mp4 import MP4, MP4Cover
from PIL import Image

from resonance_audio_builder.audio.analysis import AudioAnalyzer
from resonance_audio_builder.audio.lyrics import fetch_lyrics
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.audio.musicbrainz import get_composer_string
from resonance_audio_builder.audio.youtube import SearchResult
from resonance_audio_builder.core.config import Config, QualityMode
from resonance_audio_builder.core.exceptions import (
    CopyrightError,
    FatalError,
    GeoBlockError,
    NotFoundError,
    RecoverableError,
    YouTubeError,
)
from resonance_audio_builder.core.logger import Logger
from resonance_audio_builder.network.proxies import SmartProxyManager
from resonance_audio_builder.network.utils import USER_AGENTS, validate_cookies_file


@dataclass
class DownloadResult:
    success: bool
    bytes: int
    error: str = None
    skipped: bool = False
    fake_hq: bool = False


class AudioDownloader:
    def __init__(self, config: Config, logger: Logger, proxy_manager: Optional[SmartProxyManager] = None):
        self.cfg = config
        self.log = logger
        self._cookies_valid = validate_cookies_file(config.COOKIES_FILE)
        self.analyzer = AudioAnalyzer(logger)
        self.proxy_manager = proxy_manager
        # Note: Searcher is passed or instantiated outside usually, but manager keeps it.
        # If downloader needs to search, it should take searcher as dependency or arg,
        # but here we pass search_result directly to download().
        # However, old code had self.searcher call inside download()!
        # Wait, previous code had `self.searcher.search(track)` inside `download`.
        # This is bad dependency injection. The Manager handles search typically,
        # OR the downloader does it. In previous `downloader.py` (Step 509),
        # line 83: `search_result = self.searcher.search(track)`.
        # This implies `self.searcher` was attached to downloader instance?
        # No, wait. Line 83 `search_result = self.searcher.search(track)` fails if `self.searcher` undefined.
        # Let's check `manager.py`. It does: `self.downloader = AudioDownloader(...)`.
        # It does NOT assign searcher to downloader.
        # WAIT. In Step 504 file viewing, line 83 calls `self.searcher`.
        # BUT line 42 `def download(self, search_result: SearchResult, track: TrackMetadata...`
        # It TAKES `search_result` as ARGUMENT.
        # BUT line 83 overwrites it: `search_result = self.searcher.search(track)`?
        # Why would it search again if passed as argument?
        # Ah, looking at Step 509...
        # `def download(self, search_result: SearchResult, track: TrackMetadata...`
        # Then inside:
        # `search_result = self.searcher.search(track)`
        # This is weird. Probably my previous edit or the original code was confused.
        # If `search_result` is passed, we shouldn't search again.
        # Ideally, Manager does Search -> Result -> Downloader.
        # I will FIX this design flaw here. `download()` will take `search_result` and USE it.
        # If `search_result` is None, it might fail or we fix it to allow internal search if searcher is provided.
        # I'll stick to: Manager provides the SearchResult.

    async def validate_audio_file(self, path: Path) -> bool:
        """Valida integridad del archivo de audio usando FFmpeg (Async)"""
        if not path.exists() or path.stat().st_size < 50000:
            return False

        try:
            cmd = ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]

            # Async subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return False

            data = json.loads(stdout)
            duration = float(data.get("format", {}).get("duration", 0))
            return duration > 10.0

        except Exception:
            return False

    async def _resize_cover(self, image_data: bytes, max_size: int = 600) -> bytes:
        """Redimensiona la imagen de portada (CPU bound -> Run in executor)"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._resize_cover_sync, image_data, max_size)

    def _resize_cover_sync(self, image_data: bytes, max_size: int) -> bytes:
        try:
            img = Image.open(io.BytesIO(image_data))
            if img.width <= max_size and img.height <= max_size:
                return image_data
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(output, format="JPEG", quality=85, optimize=True)
            return output.getvalue()
        except Exception:
            return image_data

    def _prepare_download_paths(self, subfolder: str, track: TrackMetadata) -> Tuple[Path, Path, bool, bool]:
        """Calcula y crea las rutas de descarga según el modo"""
        hq_folder = Path(self.cfg.OUTPUT_FOLDER_HQ) / subfolder
        mobile_folder = Path(self.cfg.OUTPUT_FOLDER_MOBILE) / subfolder

        needed_hq = self.cfg.MODE in [QualityMode.HQ_ONLY, QualityMode.BOTH]
        needed_mobile = self.cfg.MODE in [QualityMode.MOBILE_ONLY, QualityMode.BOTH]

        if needed_hq:
            hq_folder.mkdir(parents=True, exist_ok=True)
        if needed_mobile:
            mobile_folder.mkdir(parents=True, exist_ok=True)

        filename = f"{track.safe_filename}.m4a"
        return hq_folder / filename, mobile_folder / filename, needed_hq, needed_mobile

    async def _check_existing_files(
        self, hq_path: Path, mobile_path: Path, needed_hq: bool, needed_mobile: bool
    ) -> Tuple[bool, bool]:
        """Valida si los archivos ya existen y son válidos"""
        hq_exists = False
        if needed_hq and hq_path.exists():
            hq_exists = await self.validate_audio_file(hq_path)

        mobile_exists = False
        if needed_mobile and mobile_path.exists():
            mobile_exists = await self.validate_audio_file(mobile_path)

        return hq_exists, mobile_exists

    async def download(
        self, search_result: SearchResult, track: TrackMetadata, check_quit=None, subfolder: str = ""
    ) -> DownloadResult:
        """Async download pipeline"""
        raw_path = None
        try:
            # 1. Setup paths and check existence
            hq_path, mobile_path, needed_hq, needed_mobile = self._prepare_download_paths(subfolder, track)
            hq_exists, mobile_exists = await self._check_existing_files(hq_path, mobile_path, needed_hq, needed_mobile)

            todo_hq = needed_hq and not hq_exists
            todo_mob = needed_mobile and not mobile_exists

            if not todo_hq and not todo_mob:
                return DownloadResult(True, 0, skipped=True)

            self.log.info(f"Downloading: {track.title}")
            if not search_result:
                raise YouTubeError("No search result provided")

            # 2. Download RAW (Async)
            raw_path = await self._download_raw(search_result.url, f"isrc_{track.isrc}")
            self._validate_raw(raw_path)

            if check_quit and check_quit():
                return DownloadResult(False, 0, "Cancelled", skipped=True)

            # 3. Spectral Analysis & Assets
            fake_hq = self._check_fake_hq(raw_path, track, todo_hq)
            await self._fetch_metadata_assets(track)

            # 4. Transcode and Inject
            success, total_bytes = await self._perform_transcoding_pipeline(
                raw_path, hq_path, mobile_path, track, todo_hq, todo_mob
            )

            if success:
                return DownloadResult(True, total_bytes, fake_hq=fake_hq)
            return DownloadResult(False, 0, "Transcode failed")

        except Exception as e:
            self.log.error(f"Download error {track.title}: {e}")
            return DownloadResult(False, 0, f"Error: {str(e)}")
        finally:
            self._cleanup_temp_raw(raw_path)

    def _validate_raw(self, path: Optional[Path]):
        if not path or not path.exists() or path.stat().st_size < 1024:
            raise YouTubeError("Download failed or file corrupted")

    def _check_fake_hq(self, raw_path: Path, track: TrackMetadata, needed_hq: bool) -> bool:
        if self.cfg.SPECTRAL_ANALYSIS and self.analyzer and needed_hq:
            if not self.analyzer.analyze_integrity(raw_path, self.cfg.SPECTRAL_CUTOFF):
                self.log.warning(f"Fake HQ: {track.title}")
                return True
        return False

    async def _fetch_metadata_assets(self, track: TrackMetadata):
        if track.cover_url:
            track.cover_data = await self._download_cover(track.cover_url)
            if track.cover_data:
                track.cover_data = await self._resize_cover(track.cover_data)

    async def _perform_transcoding_pipeline(
        self, raw_path, hq_path, mobile_path, track, todo_hq, todo_mob
    ) -> Tuple[bool, int]:
        tasks = []
        if todo_hq:
            tasks.append(self._transcode(raw_path, hq_path, self.cfg.QUALITY_HQ_BITRATE))
        if todo_mob:
            tasks.append(self._transcode(raw_path, mobile_path, self.cfg.QUALITY_MOBILE_BITRATE))

        results = await asyncio.gather(*tasks)

        success = True
        total_bytes = 0
        idx = 0

        if todo_hq:
            if results[idx]:
                await self._inject_metadata(hq_path, track)
                total_bytes += hq_path.stat().st_size
            else:
                success = False
            idx += 1

        if todo_mob:
            if results[idx]:
                await self._inject_metadata(mobile_path, track)
                total_bytes += mobile_path.stat().st_size
            else:
                success = False

        return success, total_bytes

    def _cleanup_temp_raw(self, raw_path: Optional[Path]):
        if raw_path and raw_path.exists():
            try:
                os.remove(raw_path)
            except Exception:
                pass

    async def _download_cover(self, url: str) -> Optional[bytes]:
        if not url:
            return None
        try:
            # Use aiohttp
            proxy = await self.proxy_manager.get_proxy_async() if self.proxy_manager else None
            proxies = {"http": proxy, "https": proxy} if proxy else {}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, proxy=proxies.get("https"), timeout=10) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception as e:
            self.log.debug(f"Error downloading cover: {e}")
        return None

    async def _inject_metadata(self, path: Path, track: TrackMetadata):
        # Mutagen is blocking file I/O. Wrap in thread.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._inject_metadata_sync, path, track)

    def _inject_metadata_sync(self, file_path: Path, track: TrackMetadata):
        """Synchronous part of metadata injection for M4A (AAC)"""
        try:
            audio = MP4(str(file_path))
            self._apply_m4a_tags(audio, track)
            audio.save()
            self.log.debug(f"Metadatos inyectados: {track.title}")
        except Exception as e:
            self.log.debug(f"Metadata error: {e}")

    def _apply_m4a_tags(self, audio: MP4, track: TrackMetadata):
        """Apply all metadata tags to M4A file using iTunes atoms"""
        # Basic tags
        if track.title:
            audio["\xa9nam"] = [track.title]

        # Artists - M4A handles lists correctly
        if track.artists:
            audio["\xa9ART"] = track.artists

        if track.album:
            audio["\xa9alb"] = [track.album]

        if track.album_artist:
            audio["aART"] = [track.album_artist]

        if track.release_date and len(track.release_date) >= 4:
            audio["\xa9day"] = [track.release_date[:4]]

        # Genre - take first from list
        if track.genres:
            first_genre = track.genre_list[0] if track.genre_list else track.genres.split(",")[0]
            audio["\xa9gen"] = [first_genre.strip().title()]

        # Label/Copyright
        if track.label:
            audio["cprt"] = [track.label]

        # Comment with Spotify URI
        if track.spotify_uri:
            audio["\xa9cmt"] = [f"Spotify: {track.spotify_uri}"]

        # BPM/Tempo
        if track.tempo > 0:
            audio["tmpo"] = [int(round(track.tempo))]

        # Track number (tuple format: track, total)
        if track.track_number:
            try:
                tn = int(track.track_number)
                audio["trkn"] = [(tn, 0)]
            except ValueError:
                pass

        # Disc number
        if track.disc_number:
            try:
                dn = int(track.disc_number)
                audio["disk"] = [(dn, 0)]
            except ValueError:
                pass

        # Cover art - M4A requires format specification
        if track.cover_data:
            self._embed_cover_m4a(audio, track.cover_data)

        # Lyrics
        try:
            lyrics = fetch_lyrics(track.artist, track.title, track.duration_seconds)
            if lyrics:
                audio["\xa9lyr"] = [lyrics]
                self.log.debug(f"Letras embebidas: {track.title}")
        except Exception as e:
            self.log.debug(f"Error obteniendo letras: {e}")

        # Composer from MusicBrainz
        try:
            if track.isrc:
                composer = get_composer_string(track.isrc)
                if composer:
                    audio["\xa9wrt"] = [composer]
                    self.log.debug(f"Compositor: {composer}")
        except Exception as e:
            self.log.debug(f"Error obteniendo compositor: {e}")

    def _embed_cover_m4a(self, audio: MP4, data: bytes):
        """Embed cover art in M4A, detecting JPEG vs PNG format"""
        try:
            # Detect format by magic bytes
            if data.startswith(b"\xff\xd8\xff"):
                fmt = MP4Cover.FORMAT_JPEG
            elif data.startswith(b"\x89PNG"):
                fmt = MP4Cover.FORMAT_PNG
            else:
                # Unknown format, skip to avoid corruption
                return

            audio["covr"] = [MP4Cover(data, imageformat=fmt)]
        except Exception as e:
            self.log.debug(f"Error embedding cover: {e}")

    def _get_ytdlp_options(self, out_tmpl: Path, proxy: Optional[str]) -> dict:
        """Configura el diccionario de opciones para yt-dlp"""
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(out_tmpl),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "socket_timeout": 15,
            "retries": 3,
            "fragment_retries": 10,
            "skip_unavailable_fragments": True,
            "geo_bypass": True,
            "http_headers": {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-us,en;q=0.5",
                "Sec-Fetch-Mode": "navigate",
            },
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"],
                    "po_token": ["web+web_embedded_player"],
                }
            },
        }

        if self.cfg.DEBUG_MODE:
            opts.update({"quiet": False, "no_warnings": False, "verbose": True})

        if proxy:
            opts["proxy"] = proxy
        if self._cookies_valid:
            opts["cookiefile"] = self.cfg.COOKIES_FILE

        return opts

    async def _download_raw(self, url: str, name: str) -> Path:
        """Async wrapper around yt-dlp download"""
        temp_dir = Path(tempfile.gettempdir())
        out_tmpl = temp_dir / f"ytraw_{name}_{int(time.time())}.%(ext)s"

        proxy = await self.proxy_manager.get_proxy_async() if self.proxy_manager else None
        opts = self._get_ytdlp_options(out_tmpl, proxy)
        opts["logger"] = self._setup_ytdlp_logger()

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._execute_ydl, url, opts, temp_dir)
        except yt_dlp.utils.DownloadError as e:
            self._handle_ytdlp_error(e, proxy)
        except Exception as e:
            if self.proxy_manager and proxy:
                self.proxy_manager.mark_failure(proxy)
            raise YouTubeError(f"Error inesperado en yt-dlp: {e}")

    def _setup_ytdlp_logger(self):
        class FileLogger:
            def _log(self, prefix, msg):
                with open("ytdlp_raw.log", "a", encoding="utf-8") as f:
                    f.write(f"[{prefix}] {msg}\n")

            def debug(self, msg):
                self._log("DEBUG", msg)

            def warning(self, msg):
                self._log("WARNING", msg)

            def error(self, msg):
                self._log("ERROR", msg)

        return FileLogger()

    def _execute_ydl(self, url, opts, temp_dir) -> Path:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise NotFoundError("yt-dlp no retornó información")

            final_path = Path(ydl.prepare_filename(info))
            if not final_path.exists():
                recovered = self._attempt_recovery(temp_dir, final_path)
                if recovered:
                    return recovered
            return final_path

    def _attempt_recovery(self, temp_dir: Path, final_path: Path) -> Optional[Path]:
        try:
            files = list(temp_dir.glob("*"))
            stem = final_path.stem
            for f in files:
                if f.stem == stem:
                    return f
        except Exception:
            pass
        return None

    def _handle_ytdlp_error(self, e: Exception, proxy: Optional[str]) -> NoReturn:
        if self.proxy_manager and proxy:
            self.proxy_manager.mark_failure(proxy)

        err_str = str(e).lower()
        if "429" in err_str or "too many requests" in err_str:
            self.log.warning("YouTube Rate Limit detected (HTTP 429). Pausing for 60s...")
            time.sleep(60)
            raise RecoverableError("Rate Limit (429) - Retrying after pause")

        if "copyright" in err_str or "blocked" in err_str:
            raise CopyrightError(f"Bloqueado: {str(e)[:50]}")
        elif "not available" in err_str or "geo" in err_str:
            raise GeoBlockError("No disponible en tu región")
        elif "sign in" in err_str or "age" in err_str:
            raise FatalError(f"Requiere login: {str(e)[:50]}")
        else:
            raise YouTubeError(f"Error descarga: {str(e)}")

    def _build_ffmpeg_cmd(self, input_path: Path, output_path: Path, bitrate: str) -> list:
        """Construye el comando ffmpeg para AAC (M4A)"""
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(input_path), "-vn"]
        if self.cfg.NORMALIZE_AUDIO:
            cmd.extend(["-filter:a", "loudnorm=I=-14:TP=-1.5:LRA=11"])

        cmd.extend(
            [
                "-acodec",
                "aac",
                "-b:a",
                f"{bitrate}k",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                "-map_metadata",
                "-1",
                str(output_path),
            ]
        )
        return cmd

    async def _transcode(self, input_path: Path, output_path: Path, bitrate: str) -> bool:
        cmd = self._build_ffmpeg_cmd(input_path, output_path, bitrate)

        try:
            # Async subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            _, stderr = await proc.communicate()

            if proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                return True

            self.log.debug(f"Transcode failed (RC={proc.returncode}): {stderr.decode(errors='ignore')}")
            if output_path.exists():
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            return False

        except Exception as e:
            self.log.debug(f"Transcode exec error: {e}")
            if output_path.exists():
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            return False
