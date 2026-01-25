"""
Resonance Audio Builder v6.0 
=============================================================
What's new in v6.0:
- External configuration (config.json)
- Adaptive rate limiting
- Visual progress bar
- MD5 file verification
- Audio normalization (ReplayGain)
- M3U playlist export
- Session history
- Desktop notifications (Windows)
"""

import csv
import os
import requests
import json
import sqlite3
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TYER, TRCK, TPOS, TPE2, TSRC, COMM, USLT
from datetime import datetime
import time
import sys
import random
import threading
import hashlib
import traceback
import atexit
import queue
import shutil
import tempfile
import subprocess
import glob
from dataclasses import dataclass, field
from typing import Optional, Dict, Set, List, Tuple, Any
from pathlib import Path

# === RICH IMPORTS ===
from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn, 
    TimeElapsedColumn, TimeRemainingColumn, TaskID
)
from rich.panel import Panel
from rich.layout import Layout
from rich.table import Table
from rich.live import Live
from rich.style import Style
from rich.theme import Theme
from rich.traceback import install as install_rich_traceback
from rich import print as rprint
from rich.text import Text
from rich.prompt import Prompt, Confirm

# Setup Rich
install_rich_traceback(show_locals=True)
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "highlight": "magenta"
})
console = Console(theme=custom_theme)


# === INYECCIÓN DE DENO AL PATH ===
_deno_path = Path.home() / '.deno' / 'bin'
if _deno_path.exists() and str(_deno_path) not in os.environ.get('PATH', ''):
    os.environ['PATH'] = str(_deno_path) + os.pathsep + os.environ.get('PATH', '')


# === EXCEPCIONES TIPADAS ===

class DownloadError(Exception):
    """Error base de descarga"""
    pass

class RecoverableError(DownloadError):
    """Error recuperable - reintentar vale la pena"""
    pass

class FatalError(DownloadError):
    """Error fatal - no reintentar (copyright, geo-block, etc)"""
    pass

class SearchError(RecoverableError):
    """Error en búsqueda de YouTube"""
    pass

class TranscodeError(RecoverableError):
    """Error en transcodificación FFmpeg"""
    pass

class TimeoutError(RecoverableError):
    """Timeout en operación"""
    pass

class NotFoundError(FatalError):
    """Video no encontrado"""
    pass

class CopyrightError(FatalError):
    """Contenido bloqueado por copyright"""
    pass

class GeoBlockError(FatalError):
    """Contenido bloqueado por región"""
    pass


# === ENUMS & CONSTANTS ===

class QualityMode:
    HQ_ONLY = 'HQ'
    MOBILE_ONLY = 'MOB'
    BOTH = 'ALL'

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
]


# === UTILIDADES ===

def clear_screen():
    """Limpia la terminal de forma robusta"""
    os.system('cls' if os.name == 'nt' else 'clear')
    console.clear()


def print_header():
    """Imprime el encabezado del programa"""
    clear_screen()
    grid = Table.grid(expand=True)
    grid.add_column(justify="center", ratio=1)
    grid.add_row(
        Panel(
            "[bold cyan]Resonance Music Downloader v6.0[/bold cyan]",
            border_style="cyan",
            padding=(1, 2)
        )
    )
    
    # OpSec Warning
    grid.add_row(
        Panel(
            "[bold red]WARNING:[/bold red] Using personal Google cookies carries risk of account termination.\nUse a burner account for cookie extraction.",
            border_style="red",
            style="bold yellow"
        )
    )
    
    console.print(grid)
    console.print()


def validate_cookies_file(filepath: str) -> bool:
    """Valida que el archivo de cookies tenga formato Netscape"""
    path = Path(filepath)
    if not path.exists():
        return False
    try:
        with open(path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            return first_line.startswith('# Netscape HTTP Cookie File') or first_line.startswith('# HTTP Cookie File')
    except:
        return False


def format_time(seconds: float) -> str:
    """Formatea segundos a mm:ss o hh:mm:ss"""
    if seconds < 0:
        return "--:--"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


def format_size(bytes_val: int) -> str:
    """Formatea bytes a MB/GB"""
    if bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_val / (1024 * 1024 * 1024):.2f} GB"



def progress_bar(current: int, total: int, width: int = 30) -> str:
    """Genera barra de progreso ASCII"""
    if total == 0:
        return "[" + "-" * width + "] 0%"
    pct = current / total
    filled = int(width * pct)
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {pct*100:.0f}%"


def calculate_md5(filepath: Path) -> str:
    """Calcula hash MD5 de un archivo"""
    hash_md5 = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except:
        return ""


def export_m3u(tracks: List[Tuple[str, str, int]], filepath: str):
    """Exporta lista de canciones a formato M3U"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            for path, title, duration in tracks:
                f.write(f"#EXTINF:{duration},{title}\n")
                f.write(f"{path}\n")
    except:
        pass


def save_history(history_file: str, session_data: dict):
    """Guarda historial de sesion"""
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except:
            pass
    
    history.append(session_data)
    
    # Mantener solo ultimas 50 sesiones
    if len(history) > 50:
        history = history[-50:]
    
    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except:
        pass


def fetch_lyrics(artist: str, title: str, duration_sec: int = 0) -> Optional[str]:
    """
    Busca letras de canciones en APIs gratuitas.
    Intenta primero LRCLIB (letras sincronizadas), luego lyrics.ovh.
    
    Args:
        artist: Nombre del artista
        title: Titulo de la cancion
        duration_sec: Duracion en segundos (para mejor match en LRCLIB)
    
    Returns:
        Letra de la cancion o None si no se encuentra
    """
    # Limpiar caracteres especiales
    clean_artist = artist.split(',')[0].strip()  # Solo primer artista
    clean_title = title.split('(')[0].split('-')[0].strip()  # Sin remixes/versions
    
    # 1. Intentar LRCLIB (letras sincronizadas .lrc)
    try:
        url = "https://lrclib.net/api/get"
        params = {
            'artist_name': clean_artist,
            'track_name': clean_title,
        }
        if duration_sec > 0:
            params['duration'] = duration_sec
        
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            # Preferir letras sincronizadas, sino las normales
            lyrics = data.get('syncedLyrics') or data.get('plainLyrics')
            if lyrics and len(lyrics) > 50:
                return lyrics
    except:
        pass
    
    # 2. Fallback a lyrics.ovh (API gratuita)
    try:
        url = f"https://api.lyrics.ovh/v1/{clean_artist}/{clean_title}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            lyrics = data.get('lyrics', '')
            if lyrics and len(lyrics) > 50:
                return lyrics.strip()
    except:
        pass
    
    return None


class RateLimiter:
    """Rate limiter adaptativo"""
    def __init__(self, min_delay: float = 0.5, max_delay: float = 2.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.current_delay = min_delay
        self.consecutive_errors = 0
        self.lock = threading.Lock()
    
    def wait(self):
        """Espera segun el delay actual"""
        time.sleep(self.current_delay + random.uniform(0, 0.5))
    
    def success(self):
        """Registra exito - reduce delay"""
        with self.lock:
            self.consecutive_errors = 0
            self.current_delay = max(self.min_delay, self.current_delay * 0.9)
    
    def error(self):
        """Registra error - aumenta delay"""
        with self.lock:
            self.consecutive_errors += 1
            self.current_delay = min(self.max_delay, self.current_delay * 1.5)
    
    def get_delay(self) -> float:
        return self.current_delay


# === DATA CLASSES ===

@dataclass
class Config:
    OUTPUT_FOLDER_HQ: str = 'Audio_HQ'
    OUTPUT_FOLDER_MOBILE: str = 'Audio_Mobile'
    ERROR_FILE: str = 'Failed_songs.txt'
    ERROR_CSV: str = 'Failed_songs.csv'
    CHECKPOINT_FILE: str = 'progress.json'
    CACHE_FILE: str = 'youtube_cache.json'
    COOKIES_FILE: str = 'cookies.txt'
    CONFIG_FILE: str = 'config.json'
    HISTORY_FILE: str = 'history.json'
    M3U_FILE: str = 'playlist.m3u'
    
    QUALITY_HQ_BITRATE: str = '320'
    QUALITY_MOBILE_BITRATE: str = '96'
    MODE: str = QualityMode.BOTH
    
    DEBUG_MODE: bool = False
    MAX_WORKERS: int = 3
    MAX_RETRIES: int = 3
    MAX_CACHE_SIZE: int = 5000
    DURATION_TOLERANCE: int = 15
    STRICT_DURATION: bool = False
    
    SEARCH_TIMEOUT: int = 30
    DOWNLOAD_TIMEOUT: int = 180
    INACTIVITY_TIMEOUT: int = 45
    CACHE_TTL_HOURS: int = 168
    
    # Nuevas opciones v5.0
    RATE_LIMIT_MIN: float = 0.5
    RATE_LIMIT_MAX: float = 2.0
    NORMALIZE_AUDIO: bool = True
    VERIFY_MD5: bool = True
    GENERATE_M3U: bool = True
    SAVE_HISTORY: bool = True
    QUIET_MODE: bool = False
    
    # v5.1 - Formato de salida: 'mp3', 'flac', o 'copy' (mantener original)
    OUTPUT_FORMAT: str = 'mp3'
    EMBED_LYRICS: bool = True
    
    @classmethod
    def load(cls, filepath: str = 'config.json') -> 'Config':
        """Carga configuracion desde archivo JSON"""
        cfg = cls()
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Mapear campos JSON a atributos
                mapping = {
                    'output_folder_hq': 'OUTPUT_FOLDER_HQ',
                    'output_folder_mobile': 'OUTPUT_FOLDER_MOBILE',
                    'quality_hq_bitrate': 'QUALITY_HQ_BITRATE',
                    'quality_mobile_bitrate': 'QUALITY_MOBILE_BITRATE',
                    'max_workers': 'MAX_WORKERS',
                    'max_retries': 'MAX_RETRIES',
                    'duration_tolerance': 'DURATION_TOLERANCE',
                    'search_timeout': 'SEARCH_TIMEOUT',
                    'cache_ttl_hours': 'CACHE_TTL_HOURS',
                    'rate_limit_delay_min': 'RATE_LIMIT_MIN',
                    'rate_limit_delay_max': 'RATE_LIMIT_MAX',
                    'normalize_audio': 'NORMALIZE_AUDIO',
                    'verify_md5': 'VERIFY_MD5',
                    'generate_m3u': 'GENERATE_M3U',
                    'save_history': 'SAVE_HISTORY',
                    'debug_mode': 'DEBUG_MODE',
                }
                for json_key, attr in mapping.items():
                    if json_key in data:
                        setattr(cfg, attr, data[json_key])
            except Exception as e:
                pass  # Usar valores por defecto si falla
        return cfg


@dataclass
class TrackMetadata:
    track_id: str
    title: str
    artist: str
    album: str = ''
    album_artist: str = ''
    release_date: str = ''
    track_number: str = ''
    disc_number: str = ''
    isrc: str = ''
    spotify_uri: str = ''
    cover_url: str = ''
    duration_ms: int = 0
    raw_data: dict = field(default_factory=dict)
    
    @classmethod
    def from_csv_row(cls, row: dict) -> 'TrackMetadata':
        r_norm = {k.strip().lower(): v for k, v in row.items()}
        r_original = {k.strip(): v for k, v in row.items()}
        
        def get_val(*keys):
            for k in keys:
                val = r_norm.get(k.lower())
                if val is not None: return val.strip()
            return ''

        isrc = get_val('isrc', 'code')
        artist = get_val('artist name(s)', 'artist', 'artist name')
        title = get_val('track name', 'track', 'title', 'name')
        
        if isrc:
            track_id = f"isrc_{isrc}"
        else:
            track_id = hashlib.md5(f"{artist}_{title}".encode()).hexdigest()[:16]
        
        duration_str = get_val('track duration (ms)', 'duration_ms', 'duration')
        duration = int(duration_str) if duration_str and duration_str.isdigit() else 0
        
        return cls(
            track_id=track_id,
            title=title,
            artist=artist,
            album=get_val('album name', 'album'),
            album_artist=get_val('album artist name(s)', 'album artist'),
            release_date=get_val('album release date', 'release date', 'year'),
            track_number=get_val('track number', 'track no'),
            disc_number=get_val('disc number', 'disc no'),
            isrc=isrc,
            spotify_uri=get_val('track uri', 'uri', 'spotify uri'),
            cover_url=get_val('album image url', 'image url', 'cover'),
            duration_ms=duration,
            raw_data=r_original
        )
    
    @property
    def duration_seconds(self) -> int:
        return self.duration_ms // 1000 if self.duration_ms else 0
    
    @property
    def safe_filename(self) -> str:
        name = f"{self.artist} - {self.title}"
        invalids = '<>:"/\\|?*'
        for char in invalids:
            name = name.replace(char, '')
        name = name.strip().rstrip('.')
        return name[:150]


@dataclass
class SearchResult:
    url: str
    title: str
    duration: int
    cached: bool = False


@dataclass
class DownloadResult:
    success: bool
    bytes: int
    error: str = None
    skipped: bool = False


# === CACHE MANAGER (SQLite) ===

class CacheManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self.lock:
            try:
                # check_same_thread=False allows sharing connection across threads if locked
                self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self.cursor = self.conn.cursor()
                self.cursor.execute('''
                    CREATE TABLE IF NOT EXISTS cache (
                        key TEXT PRIMARY KEY,
                        url TEXT,
                        title TEXT,
                        duration INTEGER,
                        timestamp REAL
                    )
                ''')
                self.conn.commit()
            except Exception as e:
                print(f"[!] Cache DB Init Error: {e}")

    def get(self, key: str, ttl_hours: int):
        if not hasattr(self, 'cursor'): return None
        limit_time = time.time() - (ttl_hours * 3600)
        with self.lock:
            try:
                self.cursor.execute("SELECT url, title, duration FROM cache WHERE key = ? AND timestamp > ?", (key, limit_time))
                row = self.cursor.fetchone()
                if row:
                    return {
                        'url': row[0],
                        'title': row[1],
                        'duration': row[2]
                    }
            except: pass
            return None

    def set(self, key: str, data: dict):
        if not hasattr(self, 'cursor'): return
        with self.lock:
            try:
                self.cursor.execute('''
                    INSERT OR REPLACE INTO cache (key, url, title, duration, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', (key, data['url'], data['title'], data.get('duration', 0), time.time()))
                self.conn.commit()
            except: pass
            
    def clear(self):
        with self.lock:
            try:
                self.cursor.execute("DELETE FROM cache")
                self.conn.commit()
            except: pass

    def count(self) -> int:
        if not hasattr(self, 'cursor'): return 0
        with self.lock:
            try:
                self.cursor.execute("SELECT COUNT(*) FROM cache")
                return self.cursor.fetchone()[0]
            except: return 0


# === LOGGING ===

class Logger:
    def __init__(self, debug: bool):
        self._debug = debug
        self._lock = threading.Lock()
    
    def set_tracker(self, tracker):
        self._tracker = tracker
        
    def _log_to_file(self, msg_clean):
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open("debug.log", "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {msg_clean}\n")
        except: pass

    def _log(self, level, msg, style):
        # File logging (strip rich markup approximation)
        msg_clean = msg.replace("[", "").replace("]", "")
        self._log_to_file(f"{level.upper()}: {msg_clean}")
        
        # UI logging
        if hasattr(self, '_tracker') and self._tracker:
            self._tracker.add_log(f"[{style}]{msg}[/{style}]")
        else:
            console.print(f"[{style}]{msg}[/{style}]")

    def info(self, msg):
        with self._lock: 
            self._log("info", f"[i] {msg}", "cyan")
    
    def debug(self, msg):
        if self._debug:
            with self._lock: 
                self._log("debug", f"    [DEBUG] {msg}", "dim white")
    
    def error(self, msg):
        with self._lock:
            self._log("error", f"[X] {msg}", "bold red")
    
    def success(self, msg):
        with self._lock:
            self._log("success", f"[+] {msg}", "bold green")
    
    def warning(self, msg):
        with self._lock:
            self._log("warning", f"[!] {msg}", "bold yellow")



# === PROGRESS TRACKER ===

class RichProgressTracker:
    def __init__(self, config: Config):
        self.cfg = config
        self.processed: Set[str] = set()
        self.lock = threading.Lock()
        
        self.ok_count = 0
        self.err_count = 0
        self.skip_count = 0
        self.bytes_total = 0
        self.start_time = 0
        
        # Rich UI components
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        )
        self.active_downloads = Table.grid(expand=True)
        self.active_downloads.add_column(style="dim")
        self.active_downloads.add_column(justify="right")
        
        # Log buffer
        from collections import deque
        self.log_buffer = deque(maxlen=8)
        self.log_panel = None
        
        self.layout = None
        self.live = None
        self.main_task = None
        self.download_tasks: Dict[str, TaskID] = {}
        
        self._load()
    
    def _load(self):
        if os.path.exists(self.cfg.CHECKPOINT_FILE):
            try:
                with open(self.cfg.CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.processed = set(data)
            except: pass
    
    def save(self):
        with self.lock:
            try:
                with open(self.cfg.CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(list(self.processed), f)
            except: pass

    def reset_stats(self):
        with self.lock:
            self.ok_count = 0
            self.err_count = 0
            self.skip_count = 0
            self.bytes_total = 0
            self.start_time = time.time()

    def reset_all(self):
        with self.lock:
            self.processed.clear()
            self.save()
            self.reset_stats()
            
    def get_stats_string(self) -> str:
        with self.lock:
            return f"OK: {self.ok_count} | Skp: {self.skip_count} | Err: {self.err_count}"

    def start(self, total: int):
        self.start_time = time.time()
        self.main_task = self.progress.add_task("[cyan]Total Progress", total=total)
        
        # Crear layout
        from rich.console import Group
        from rich.layout import Layout
        
        # Initial logs
        panels = [
            Panel(self.progress, title="Overall Progress", border_style="cyan"),
            Panel(self.active_downloads, title="Active Downloads", border_style="green")
        ]
        
        if self.cfg.DEBUG_MODE:
            self.log_text = Text("\n".join(self.log_buffer) if self.log_buffer else "[dim]Waiting for logs...[/dim]")
            panels.append(Panel(self.log_text, title="Live Logs", border_style="dim", height=10))
        
        self.layout = Group(*panels)
        self.live = Live(self.layout, refresh_per_second=4, console=console) # Reduced refresh rate
        self.live.start()

    def add_log(self, msg: str):
        self.log_buffer.append(msg)
        
        # Keep buffer small
        if len(self.log_buffer) > 50:
             self.log_buffer = self.log_buffer[-50:]
             
        if hasattr(self, 'log_text'):
            start_idx = max(0, len(self.log_buffer) - 10)
            # Remove rich tags for cleaner log history in UI
            clean_text = "\n".join(self.log_buffer[start_idx:])
            self.log_text.plain = clean_text # Update Text object in-place
    
    def stop(self):
        if self.live:
            self.live.stop()

    def add_download_task(self, name: str, total_bytes: int = 100) -> TaskID:
        # Añadir al progress
        task_id = self.progress.add_task(f"[green]Downloading {name[:20]}", total=total_bytes)
        return task_id
    
    def update_download(self, task_id: TaskID, advance: int):
        self.progress.update(task_id, advance=advance)
    
    def remove_task(self, task_id: TaskID):
        try:
            self.progress.remove_task(task_id)
        except: pass

    def mark(self, track_id: str, status: str, bytes_n: int = 0):
        with self.lock:
            self.processed.add(track_id)
            if status == 'ok': self.ok_count += 1
            elif status == 'skip': self.skip_count += 1
            elif status == 'err': self.err_count += 1
            self.bytes_total += bytes_n
            
            if self.main_task is not None:
                self.progress.update(self.main_task, advance=1)
    
    def is_done(self, track_id: str) -> bool:
        with self.lock:
            return track_id in self.processed

    def get_stats_table(self) -> Table:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Status", style="dim")
        table.add_column("Count")
        table.add_row("Success", f"[green]{self.ok_count}[/green]")
        table.add_row("Skipped", f"[yellow]{self.skip_count}[/yellow]")
        table.add_row("Failed", f"[red]{self.err_count}[/red]")
        return table


class YouTubeSearcher:
    def __init__(self, config: Config, logger: Logger, cache_manager: CacheManager):
        self.cfg = config
        self.log = logger
        self.app_cache = cache_manager
        self.cache: Dict[str, dict] = {}
        self.lock = threading.Lock()
        self._cookies_valid = validate_cookies_file(config.COOKIES_FILE)
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cfg.CACHE_FILE):
            try:
                with open(self.cfg.CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    now = time.time()
                    ttl = self.cfg.CACHE_TTL_HOURS * 3600
                    self.cache = {k: v for k, v in data.items() 
                                  if now - v.get('_ts', 0) < ttl}
                    self.log.debug(f"Caché cargado: {len(self.cache)} entradas")
            except Exception as e:
                self.log.debug(f"Error cargando caché: {e}")

    def _save_cache(self):
        with self.lock:
            # Limpiar si excede límite
            if len(self.cache) > self.cfg.MAX_CACHE_SIZE:
                keys = sorted(self.cache.keys(), key=lambda k: self.cache[k].get('_ts', 0))
                for k in keys[:int(len(keys) * 0.2)]:
                    del self.cache[k]
            
            try:
                with open(self.cfg.CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.cache, f, ensure_ascii=False)
            except Exception as e:
                self.log.debug(f"Error guardando caché: {e}")

    def search(self, track: TrackMetadata, attempt: int = 1) -> SearchResult:
        """Busca una canción en YouTube con estrategia múltiple"""
        
        # 1. Intentar por ISRC primero (más preciso)
        if track.isrc:
            # Check SQLite Cache for ISRC
            if self.app_cache:
                cached = self.app_cache.get(f"isrc_{track.isrc}", ttl_hours=24*30)
                if cached:
                    self.log.debug(f"Cache hit (ISRC): {track.title}")
                    return SearchResult(cached['url'], cached['title'], cached['duration'], cached=True)
            
            result = self._lookup(f"isrc_{track.isrc}", f'"{track.isrc}"', track.duration_seconds)
            if result:
                return result
        
        # 2. Búsqueda por artista + título
        query = f"{track.artist} - {track.title} Audio"
        cache_key = query.lower().strip()[:100]
        
        if self.app_cache:
            cached = self.app_cache.get(cache_key, ttl_hours=24*7)
            if cached:
                 self.log.debug(f"Cache hit: {track.title}")
                 return SearchResult(cached['url'], cached['title'], cached['duration'], cached=True)

        result = self._lookup(cache_key, query, track.duration_seconds)
        if result:
            return result
        
        # 3. Búsqueda alternativa (sin "Audio")
        if attempt < 2:
            query_alt = f"{track.artist} {track.title} Topic"
            result = self._lookup(query_alt.lower()[:100], query_alt, track.duration_seconds)
            if result:
                return result
        
        raise NotFoundError(f"No encontrado: {track.artist} - {track.title}")

    def _lookup(self, cache_key: str, query: str, duration: int) -> Optional[SearchResult]:
        # Búsqueda web
        opts = {
            'quiet': True, 
            'no_warnings': True, 
            'extract_flat': True, 
            'noplaylist': True,
            'socket_timeout': self.cfg.SEARCH_TIMEOUT,
            'http_headers': {'User-Agent': random.choice(USER_AGENTS)}
        }
        
        if self._cookies_valid:
            opts['cookiefile'] = self.cfg.COOKIES_FILE
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                results = ydl.extract_info(f"ytsearch5:{query}", download=False)
                
                if not results or 'entries' not in results:
                    return None
                
                entries = [e for e in results['entries'] if e]
                if not entries:
                    return None
                
                # Filtrar por duración si tenemos referencia
                best_entry = None
                best_diff = float('inf')
                
                for entry in entries:
                    entry_duration = entry.get('duration', 0)
                    entry_title = entry.get('title', '').lower()
                    
                    # Excluir covers, remixes, etc. (a menos que la búsqueda los incluya)
                    excludes = ['cover', 'remix', 'live', 'karaoke', 'instrumental']
                    if any(x in entry_title for x in excludes):
                        if not any(x in query.lower() for x in excludes):
                            continue
                    
                    if duration and entry_duration:
                        diff = abs(entry_duration - duration)
                        if diff <= self.cfg.DURATION_TOLERANCE and diff < best_diff:
                            best_diff = diff
                            best_entry = entry
                    elif not best_entry:
                        best_entry = entry
                
                if not best_entry and entries:
                    best_entry = entries[0]
                
                if best_entry:
                    url = best_entry.get('webpage_url') or best_entry.get('url')
                    sr = SearchResult(
                        url=url,
                        title=best_entry.get('title', ''),
                        duration=best_entry.get('duration', 0)
                    )
                    
                    self.log.debug(f"Encontrado: {sr.title[:50]}")
                    
                    # Guardar en SQLite
                    if self.app_cache:
                        self.app_cache.set(cache_key, {
                            'url': sr.url,
                            'title': sr.title,
                            'duration': sr.duration
                        })
                    
                    return sr
                    
        except Exception as e:
            self.log.debug(f"Error búsqueda: {e}")
        
        return None


# === AUDIO DOWNLOADER ===

class AudioDownloader:
    def __init__(self, config: Config, logger: Logger):
        self.cfg = config
        self.log = logger
        self._cookies_valid = validate_cookies_file(config.COOKIES_FILE)
    
    def download(self, search_result: SearchResult, track: TrackMetadata, 
                 stop_check: callable) -> DownloadResult:
        """Descarga y transcodifica una canción"""
        
        # Determinar qué archivos generar
        outputs = []
        hq_path = Path(self.cfg.OUTPUT_FOLDER_HQ) / f"{track.safe_filename}.mp3"
        mob_path = Path(self.cfg.OUTPUT_FOLDER_MOBILE) / f"{track.safe_filename}.mp3"
        
        if self.cfg.MODE in [QualityMode.HQ_ONLY, QualityMode.BOTH]:
            outputs.append((hq_path, self.cfg.QUALITY_HQ_BITRATE))
        if self.cfg.MODE in [QualityMode.MOBILE_ONLY, QualityMode.BOTH]:
            outputs.append((mob_path, self.cfg.QUALITY_MOBILE_BITRATE))
        
        # Verificar si ya existen todos
        all_exist = all(p.exists() and p.stat().st_size > 0 for p, _ in outputs)
        if all_exist:
            return DownloadResult(True, 0, skipped=True)
        
        # Descargar audio raw
        if stop_check():
            raise RecoverableError("Cancelado por usuario")
        
        raw_path = self._download_raw(search_result.url, track.safe_filename)
        total_bytes = 0
        
        try:
            # Transcodificar a cada formato necesario
            for out_path, bitrate in outputs:
                if stop_check():
                    raise RecoverableError("Cancelado por usuario")
                
                out_path.parent.mkdir(parents=True, exist_ok=True)
                
                if not out_path.exists() or out_path.stat().st_size == 0:
                    self.log.debug(f"Transcodificando a {bitrate}kbps...")
                    if self._transcode(raw_path, out_path, bitrate):
                        total_bytes += out_path.stat().st_size
                    else:
                        raise TranscodeError(f"FFmpeg falló para {bitrate}kbps")
            
            return DownloadResult(True, total_bytes)
            
        finally:
            # Limpiar archivo temporal
            if raw_path.exists():
                try: 
                    raw_path.unlink()
                except: 
                    pass
    
    def _download_raw(self, url: str, name: str) -> Path:
        """Descarga audio raw de YouTube"""
        temp_dir = Path(tempfile.gettempdir())
        out_tmpl = temp_dir / f"ytraw_{name}_{int(time.time())}.%(ext)s"
        
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(out_tmpl),
            'quiet': True, 
            'no_warnings': True, 
            'noprogress': True,
            'socket_timeout': 15, 
            'retries': 3,
            'fragment_retries': 3,
            'skip_unavailable_fragments': True,
            'http_headers': {'User-Agent': random.choice(USER_AGENTS)}
        }
        
        if self._cookies_valid:
            opts['cookiefile'] = self.cfg.COOKIES_FILE
        
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
        
        Args:
            input_path: Archivo de entrada (webm, m4a, etc)
            output_path: Archivo MP3 de salida
            bitrate: Bitrate en kbps (ej: "320")
        
        Returns:
            True si la transcodificacion fue exitosa
        """
        # Construir comando base
        cmd = [
            'ffmpeg', '-y', '-v', 'error',
            '-i', str(input_path),
            '-vn',
        ]
        
        # Agregar normalizacion EBU R128 si esta habilitada
        # loudnorm: I=-14 (loudness target), TP=-1.5 (true peak), LRA=11 (loudness range)
        if self.cfg.NORMALIZE_AUDIO:
            cmd.extend(['-filter:a', 'loudnorm=I=-14:TP=-1.5:LRA=11'])
        
        # Parametros de codificacion MP3
        cmd.extend([
            '-acodec', 'libmp3lame',
            '-b:a', f'{bitrate}k',
            '-ar', '44100',
            '-ac', '2',
            '-map_metadata', '-1',
            str(output_path)
        ])
        
        try:
            # Aumentar timeout a 5 minutos y no checkear error code inmediatamente
            # ya que ffmpeg puede emitir warnings no fatales
            result = subprocess.run(
                cmd, 
                timeout=300, 
                check=False, 
                capture_output=True,
                creationflags=0x08000000 if os.name == 'nt' else 0
            )
            
            # Verificar existencia del archivo y tamaño > 0
            if output_path.exists() and output_path.stat().st_size > 0: # Check size > 0 only
                return True
            
            # Si falló, loggear stderr (solo si no existe el archivo)
            err_msg = result.stderr.decode(errors='ignore') if result.stderr else "Unknown error"
            self.log.debug(f"FFmpeg falló (RC={result.returncode}): {err_msg[:200]}")
            
            # Limpiar archivo corrupto/vacio
            if output_path.exists():
                try: os.remove(output_path)
                except: pass
                
            return False

        except subprocess.TimeoutExpired:
            self.log.debug("Timeout en FFmpeg (300s)")
            if output_path.exists():
                try: os.remove(output_path)
                except: pass
            return False
            
        except Exception as e:
            self.log.debug(f"Error transcodificacion: {e}")
            if output_path.exists():
                try: os.remove(output_path)
                except: pass
            return False


# === METADATA WRITER ===

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
            except:
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
                audio.tags.add(COMM(encoding=3, lang='eng', desc='', 
                                   text=f"Spotify: {meta.spotify_uri}"))
            
            # Caratula
            if meta.cover_url:
                try:
                    resp = requests.get(meta.cover_url, timeout=10)
                    if resp.status_code == 200 and len(resp.content) > 0:
                        audio.tags.add(APIC(
                            encoding=3,
                            mime='image/jpeg',
                            type=3,
                            desc='Cover',
                            data=resp.content
                        ))
                except Exception as e:
                    self.log.debug(f"Error descargando caratula: {e}")
            
            # Letras (USLT tag)
            try:
                lyrics = fetch_lyrics(meta.artist, meta.title, meta.duration_seconds)
                if lyrics:
                    audio.tags.add(USLT(
                        encoding=3,
                        lang='eng',
                        desc='',
                        text=lyrics
                    ))
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


# === KEYBOARD CONTROLLER ===

class KeyboardController:
    """Controlador de teclado para comandos en tiempo real"""
    
    def __init__(self, logger: Logger):
        self.log = logger
        self.pause_event = threading.Event()
        self.pause_event.set()  # No pausado
        self.quit_event = threading.Event()
        self.skip_event = threading.Event()
        self._thread = None
        self._running = False
    
    def start(self):
        """Inicia el listener de teclado"""
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Detiene el listener"""
        self._running = False
    
    def is_paused(self) -> bool:
        return not self.pause_event.is_set()
    
    def should_quit(self) -> bool:
        return self.quit_event.is_set()
    
    def should_skip(self) -> bool:
        if self.skip_event.is_set():
            self.skip_event.clear()
            return True
        return False
    
    def wait_if_paused(self):
        """Bloquea si está pausado"""
        self.pause_event.wait()
    
    def _listen(self):
        """Loop de escucha de teclado"""
        if os.name == 'nt':
            self._listen_windows()
        else:
            self._listen_unix()
    
    def _listen_windows(self):
        try:
            import msvcrt
            while self._running and not self.quit_event.is_set():
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8', errors='ignore').upper()
                    self._handle_key(key)
                time.sleep(0.1)
        except:
            pass
    
    def _listen_unix(self):
        try:
            import sys
            import select
            import tty
            import termios
            
            old_settings = termios.tcgetattr(sys.stdin.fileno())
            
            def restore():
                try:
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)
                except:
                    pass
            
            atexit.register(restore)
            
            while self._running and not self.quit_event.is_set():
                try:
                    tty.setraw(sys.stdin.fileno())
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if rlist:
                        key = sys.stdin.read(1).upper()
                        self._handle_key(key)
                finally:
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)
                time.sleep(0.05)
        except:
            pass
    
    def _handle_key(self, key: str):
        if key == 'P':
            if self.pause_event.is_set():
                self.pause_event.clear()
                print("\n⏸  PAUSADO - Presiona P para continuar")
            else:
                self.pause_event.set()
                print("\n▶  REANUDADO")
        elif key == 'S':
            self.skip_event.set()
            print("\n⏭  Saltando...")
        elif key == 'Q':
            self.quit_event.set()
            print("\n⏹  Finalizando...")


# === DOWNLOAD MANAGER ===

class DownloadManager:
    """Orquestador principal de descargas"""
    
    def __init__(self, config: Config, cache_manager: CacheManager):
        self.cfg = config
        self.log = Logger(config.DEBUG_MODE)
        self.cache = cache_manager
        self.tracker = RichProgressTracker(self.cfg)
        self.log.set_tracker(self.tracker) # Link logger to tracker UI
        self.downloader = AudioDownloader(self.cfg, self.log)
        self.searcher = YouTubeSearcher(self.cfg, self.log, self.cache)
        self.metadata_writer = MetadataWriter(self.log)
        self.keyboard = KeyboardController(self.log)
        
        # Limpiar terminal al inicio
        console.clear()
        self.queue: queue.Queue = queue.Queue()
        self.failed_tracks: List[Tuple[TrackMetadata, str]] = []
        self._print_lock = threading.Lock()
    
    def run(self, tracks: List[TrackMetadata]):
        """Ejecuta la descarga de todas las canciones"""
        
        # Filtrar ya procesadas
        pending = [t for t in tracks if not self.tracker.is_done(t.track_id)]
        
        if not pending:
            print("\n✓ ¡Todas las canciones ya están descargadas!")
            return
        
        clear_screen()
        print_header()
        
        self.tracker.total_pending = len(pending)
        self.tracker.reset_stats()
        
        # Mostrar info de canciones
        table = Table(title=f"Download Queue ({len(pending)} pending)", expand=True, box=None)
        table.add_column("Track", style="bold white")
        table.add_column("Artist", style="cyan")
        table.add_column("Status", justify="right")
        
        # Mostrar primero las ya descargadas (primeras 10)
        done_count = 0
        for t in tracks:
            if self.tracker.is_done(t.track_id):
                if done_count < 10:
                    table.add_row(t.title, t.artist, "[green]✔ Downloaded[/green]")
                done_count += 1
        
        if done_count > 10:
             table.add_row("...", "...", f"[dim]+ {done_count - 10} more done[/dim]")

        # Mostrar las pendientes (primeras 20)
        pending_count = 0
        for t in pending:
            if pending_count < 20:
                table.add_row(t.title, t.artist, "[yellow]⏳ Pending[/yellow]")
            pending_count += 1
            
        if pending_count > 20:
            table.add_row("...", "...", f"[dim]+ {pending_count - 20} more pending[/dim]")

        console.print(Panel(table, border_style="blue"))

        # Summary Panel
        summary = Table.grid(expand=True, padding=(0, 2))
        summary.add_column(style="bold")
        summary.add_column()
        summary.add_row("Total Tracks:", str(len(tracks)))
        summary.add_row("Already Done:", f"[green]{done_count}[/green]")
        summary.add_row("To Download:", f"[yellow]{len(pending)}[/yellow]")
        summary.add_row("Quality Mode:", f"[magenta]{self.cfg.MODE}[/magenta]")
        
        console.print(Panel(summary, title="Batch Summary", border_style="green"))
        
        if not Confirm.ask("Start download?", default=True):
            console.print("[yellow]Cancelled by user.[/yellow]")
            return

        print()
        
        # Start Live Display
        self.tracker.start(len(pending))
        
        # Llenar cola
        for t in pending:
            self.queue.put(t)
        
        # Iniciar keyboard listener
        self.keyboard.start()
        
        # Iniciar workers
        workers = []
        for i in range(self.cfg.MAX_WORKERS):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            workers.append(t)
        
        # Esperar finalización
        try:
            while not self.queue.empty() and not self.keyboard.should_quit():
                time.sleep(0.5)
            
            # Vaciar cola si salimos prematuramente
            if self.keyboard.should_quit():
                while not self.queue.empty():
                    try:
                        self.queue.get_nowait()
                        self.queue.task_done()
                    except:
                        break
            
            self.queue.join()
            
            self.queue.join()
            
        except KeyboardInterrupt:
            # Quit handled by signal in App or here
            self.keyboard.quit_event.set()
        
        finally:
            self.keyboard.stop()
            self.tracker.stop() # Stop Live display
            self.tracker.save()
            self._save_failed()
            self._print_summary()
    
    def _worker(self):
        """Thread worker de descarga"""
        while not self.keyboard.should_quit():
            try:
                track = self.queue.get(timeout=1)
            except queue.Empty:
                continue
            
            if track is None:
                self.queue.task_done()
                break
            
            # Esperar si está pausado
            self.keyboard.wait_if_paused()
            
            # Verificar skip
            if self.keyboard.should_skip():
                self.tracker.mark(track.track_id, 'skip')
                self.queue.task_done()
                continue
            
            # Procesar canción
            attempt = 0
            success = False
            last_error = ""
            
            while attempt < self.cfg.MAX_RETRIES and not success:
                if self.keyboard.should_quit():
                    break
                
                attempt += 1
                
                try:
                    # 1. Buscar
                    search_result = self.searcher.search(track)
                    
                    # 2. Descargar
                    task_id = self.tracker.add_download_task(track.title)
                    self.tracker.active_downloads.add_row(f"{track.artist} - {track.title}", "Downloading...")
                    
                    try:
                        result = self.downloader.download(
                            search_result, track,
                            lambda: self.keyboard.should_quit()
                        )
                    finally:
                        self.tracker.remove_task(task_id)
                    
                    # 3. Metadatos (Siempre intentar escribir, incluso si ya estaba descargado)
                    folders = []
                    if self.cfg.MODE in [QualityMode.HQ_ONLY, QualityMode.BOTH]:
                        folders.append(self.cfg.OUTPUT_FOLDER_HQ)
                    if self.cfg.MODE in [QualityMode.MOBILE_ONLY, QualityMode.BOTH]:
                        folders.append(self.cfg.OUTPUT_FOLDER_MOBILE)
                    
                    for folder in folders:
                        mp3_path = Path(folder) / f"{track.safe_filename}.mp3"
                        if mp3_path.exists():
                            self.metadata_writer.write(mp3_path, track)
                    
                    # Éxito
                    status = 'skip' if result.skipped else 'ok'
                    self.tracker.mark(track.track_id, status, result.bytes)
                    success = True
                    
                except FatalError as e:
                    last_error = str(e)
                    self.log.debug(f"Error fatal: {e}")
                    break  # No reintentar errores fatales
                    
                except RecoverableError as e:
                    last_error = str(e)
                    if attempt < self.cfg.MAX_RETRIES:
                        self.log.debug(f"Reintento {attempt}/{self.cfg.MAX_RETRIES}: {e}")
                        time.sleep(2 * attempt)  # Backoff exponencial
                    
                except Exception as e:
                    last_error = str(e)
                    self.log.debug(f"Error inesperado: {traceback.format_exc()}")
                    break
            
            if not success and not self.keyboard.should_quit():
                self.tracker.mark(track.track_id, 'err')
                self.failed_tracks.append((track, last_error))
            
            self.queue.task_done()
            
            # Guardar checkpoint periódicamente
            processed = self.tracker.ok_count + self.tracker.err_count + self.tracker.skip_count
            if processed % 5 == 0:
                self.tracker.save()
    
    
    def _print_progress(self, track: TrackMetadata, symbol: str, msg: str):
        pass # Deprecated by Rich UI
    
    def _save_failed(self):
        """Guarda canciones fallidas"""
        if not self.failed_tracks:
            return
        
        # TXT legible
        with open(self.cfg.ERROR_FILE, 'w', encoding='utf-8') as f:
            f.write(f"CANCIONES FALLIDAS - {datetime.now()}\n")
            f.write("=" * 60 + "\n\n")
            for track, error in self.failed_tracks:
                f.write(f"• {track.artist} - {track.title}\n")
                f.write(f"  Error: {error}\n\n")
        
        # CSV para reintentar
        with open(self.cfg.ERROR_CSV, 'w', encoding='utf-8', newline='') as f:
            if self.failed_tracks:
                sample = self.failed_tracks[0][0].raw_data
                fieldnames = list(sample.keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for track, _ in self.failed_tracks:
                    writer.writerow(track.raw_data)
    
    def _print_summary(self):
        """Imprime resumen final con Rich"""
        elapsed = time.time() - self.tracker.start_time
        
        console.print("\n")
        console.print(Panel(
            self.tracker.get_stats_table(),
            title=f"Final Summary - {format_time(elapsed)} - {format_size(self.tracker.bytes_total)}",
            border_style="green"
        ))
        
        if self.failed_tracks:
            console.print(f"[yellow]Failed tracks saved to: {self.cfg.ERROR_FILE}[/yellow]")
        
        # Guardar historial
        session_data = {
            'date': datetime.now().isoformat(),
            'success': self.tracker.ok_count,
            'skipped': self.tracker.skip_count,
            'failed': self.tracker.err_count,
            'duration_sec': int(elapsed),
            'bytes': self.tracker.bytes_total,
            'mode': self.cfg.MODE
        }
        if self.cfg.SAVE_HISTORY:
            save_history(self.cfg.HISTORY_FILE, session_data)
        
        # Exportar playlist M3U
        if self.cfg.GENERATE_M3U and self.tracker.ok_count > 0:
            try:
                # Recopilar archivos descargados
                m3u_tracks = []
                folder = self.cfg.OUTPUT_FOLDER_HQ if self.cfg.MODE != QualityMode.MOBILE_ONLY else self.cfg.OUTPUT_FOLDER_MOBILE
                if os.path.exists(folder):
                    for f in os.listdir(folder):
                        if f.endswith('.mp3'):
                            path = os.path.join(folder, f)
                            title = f.replace('.mp3', '')
                            m3u_tracks.append((path, title, 0))
                
                if m3u_tracks:
                    export_m3u(m3u_tracks, self.cfg.M3U_FILE)
                    print(f"  [i] Playlist M3U: {self.cfg.M3U_FILE}")
            except:
                pass
        
        print("=" * 60)


# === MAIN APP ===

class App:
    def __init__(self):
        self.cfg = Config.load()  # Carga desde config.json si existe
        self.log = Logger(self.cfg.DEBUG_MODE)
        self.tracker = RichProgressTracker(self.cfg)
        
        # Init SQLite Cache (replaces old JSON cache)
        try:
            self.cache = CacheManager("cache.db")
        except Exception as e:
            self.log.error(f"Failed to init cache: {e}")
            self.cache = None
        self.rate_limiter = RateLimiter(self.cfg.RATE_LIMIT_MIN, self.cfg.RATE_LIMIT_MAX)
    
    def _check_dependencies(self) -> bool:
        if not shutil.which('ffmpeg'):
            print("\n[ERROR] FFmpeg no está instalado.")
            print("        Descárgalo de: https://ffmpeg.org/download.html")
            return False
        return True
    
    def _show_status(self):
        cookies_status = "[bold green]OK[/bold green]" if self._check_dependencies_silent() else "[yellow]Missing[/yellow]"
        
        # Stats
        cache_count = self.cache.count() if self.cache else 0
        progress_count = len(self.tracker.processed)
        
        # Grid layout
        grid = Table.grid(expand=True, padding=(0, 2))
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        
        # Left Panel: System
        deno_ok = shutil.which('deno') or os.path.exists(Path.home() / '.deno' / 'bin' / 'deno.exe')
        sys_info = f"""[bold]FFmpeg:[/bold]    [green]Installed[/green]
[bold]Deno:[/bold]      {'[green]Installed[/green]' if deno_ok else '[dim]Optional[/dim]'}
[bold]Cookies:[/bold]   {cookies_status}"""
        
        # Right Panel: Data
        data_info = f"""[bold]Cache:[/bold]     {cache_count} entries (SQLite)
[bold]History:[/bold]   {progress_count} songs
[bold]Quality:[/bold]   {self.cfg.MODE}"""

        grid.add_row(
            Panel(sys_info, title="System Status", border_style="blue"),
            Panel(data_info, title="Data Metrics", border_style="magenta")
        )
        
        console.print(grid)

    def _check_dependencies_silent(self) -> bool:
        return validate_cookies_file(self.cfg.COOKIES_FILE)
    
    def _select_csv(self) -> Optional[str]:
        clear_screen()
        print_header()
        
        csvs = [c for c in glob.glob("*.csv") if 'fallidas' not in c.lower()]
        
        if not csvs:
            console.print(Panel("[yellow]No CSV files found in the current directory.[/yellow]\n\nExport playlists from: [link=https://exportify.net/]https://exportify.net/[/link]", title="Warning", border_style="yellow"))
            return None
        
        if len(csvs) == 1:
            console.print(Panel(f"[bold green]Selected file:[/bold green] {csvs[0]}", border_style="green"))
            return csvs[0]
        
        table = Table(title="Select CSV File", show_header=True, header_style="bold magenta", expand=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("Filename", style="bold cyan")
        table.add_column("Size", justify="right")
        
        for i, f in enumerate(csvs):
            size_mb = os.path.getsize(f) / 1024
            table.add_row(str(i+1), f, f"{size_mb:.1f} KB")
            
        console.print(table)
        
        choices = [str(i+1) for i in range(len(csvs))]
        sel = Prompt.ask("Choose a file", choices=choices, default="1")
        return csvs[int(sel)-1]
    
    def _select_quality(self):
        clear_screen()
        print_header()
        
        grid = Table.grid(expand=True, padding=(0, 2))
        grid.add_column(ratio=1)
        grid.add_column(ratio=3)
        
        grid.add_row("[bold cyan]1.[/bold cyan] High Quality", "320kbps MP3 (Best for PC/Hi-Fi)")
        grid.add_row("[bold cyan]2.[/bold cyan] Mobile", "96kbps MP3 (Save space)")
        grid.add_row("[bold cyan]3.[/bold cyan] Both", "High Quality + Mobile versions")
        
        console.print(Panel(grid, title="Select Quality", border_style="cyan"))
        
        sel = Prompt.ask("Option", choices=["1", "2", "3"], default="3")
        
        if sel == '1': 
            self.cfg.MODE = QualityMode.HQ_ONLY
            console.print("[dim]Selected: High Quality only[/dim]")
        elif sel == '2':
            self.cfg.MODE = QualityMode.MOBILE_ONLY
            console.print("[dim]Selected: Mobile only[/dim]")
        elif sel == '3':
            self.cfg.MODE = QualityMode.BOTH
            console.print("[dim]Selected: Both versions[/dim]")
    
    def _read_csv(self, filepath: str) -> List[dict]:
        encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
        
        for enc in encodings:
            try:
                with open(filepath, 'r', encoding=enc) as f:
                    sample = f.read(1024)
                    f.seek(0)
                    if '\0' in sample: continue
                    
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    if len(rows) > 0 and reader.fieldnames:
                        self.log.info(f"[i] Codificación: {enc}")
                        return rows
            except: continue
        
        print("[!] Error leyendo CSV.")
        return []
    
    def _start_download(self):
        csv_file = self._select_csv()
        if not csv_file:
            input("\nENTER para continuar...")
            return
        
        self._select_quality()
        
        rows = self._read_csv(csv_file)
        if not rows:
            input("\nENTER para continuar...")
            return
        
        tracks = [TrackMetadata.from_csv_row(row) for row in rows]
        
        # Eliminar duplicados
        unique = {}
        for t in tracks:
            if t.track_id not in unique:
                unique[t.track_id] = t
        
        tracks = list(unique.values())
        
        print(f"\n[i] {len(tracks)} canciones únicas detectadas")
        
        # Ejecutar descarga
        manager = DownloadManager(self.cfg, self.cache)
        manager.run(tracks)
        
        input("\nENTER para continuar...")
    
    def _retry_failed(self):
        """Reintenta descargar canciones fallidas"""
        clear_screen()
        print_header()
        
        if not os.path.exists(self.cfg.ERROR_CSV):
            print("\n[!] No hay archivo de canciones fallidas.")
            print(f"    ({self.cfg.ERROR_CSV} no existe)")
            input("\nENTER para continuar...")
            return
        
        rows = self._read_csv(self.cfg.ERROR_CSV)
        if not rows:
            print("\n[!] El archivo de fallidas esta vacio.")
            input("\nENTER para continuar...")
            return
        
        tracks = [TrackMetadata.from_csv_row(row) for row in rows]
        
        # Eliminar de procesadas para que se reintenten
        for t in tracks:
            if t.track_id in self.tracker.processed:
                self.tracker.processed.remove(t.track_id)
        self.tracker.save()
        
        # Eliminar duplicados
        unique = {}
        for t in tracks:
            if t.track_id not in unique:
                unique[t.track_id] = t
        
        tracks = list(unique.values())
        
        print(f"\n[i] {len(tracks)} canciones fallidas a reintentar")
        
        self._select_quality()
        
        # Ejecutar descarga
        manager = DownloadManager(self.cfg, self.cache)
        manager.run(tracks)
        
        input("\nENTER para continuar...")
    
    def _clear_cache(self):
        clear_screen()
        print_header()
        
        table = Table(title="Clear Data", show_header=False, box=None)
        table.add_row("[1] Clear Search Cache (SQLite/YouTube)")
        table.add_row("[2] Clear Progress (Reset done list)")
        table.add_row("[3] Clear All")
        table.add_row("[0] Cancel")
        
        console.print(Panel(table, border_style="red"))
        
        sel = Prompt.ask("Option", choices=["0", "1", "2", "3"], default="0")
        
        if sel == '0':
            console.print("[yellow]Cancelled.[/yellow]")
            Prompt.ask("\nPress ENTER to continue")
            return

        deleted = []
        if sel in ['1', '3']:
            self.cache.clear()
            deleted.append("Cache (SQLite)")
        
        if sel in ['2', '3']:
            if os.path.exists(self.cfg.CHECKPOINT_FILE):
                os.remove(self.cfg.CHECKPOINT_FILE)
                self.tracker.reset_all()
                deleted.append("Progress")
        
        if deleted:
            console.print(f"[green]Deleted: {', '.join(deleted)}[/green]")
        else:
            console.print("[dim]Nothing to delete.[/dim]")
            
        Prompt.ask("\nPress ENTER to continue")
    
    def _notify_end(self):
        """Sonido de notificacion"""
        try:
            if os.name == 'nt':
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else:
                print('\a')
        except: pass
    
    def run(self):
        if not self._check_dependencies():
            input("\nPress ENTER to exit...")
            return
        
        while True:
            print_header()
            self._show_status()
            
            # Menu Principal con Grid
            menu_table = Table(show_header=False, box=None, padding=(0, 2))
            menu_table.add_row("[bold cyan]1.[/bold cyan] Start download from CSV", style="bold")
            menu_table.add_row("[bold cyan]2.[/bold cyan] Retry failed songs")
            menu_table.add_row("[bold cyan]3.[/bold cyan] Clear cache/progress")
            menu_table.add_row("[bold red]4.[/bold red] Exit")
            
            console.print(Panel(menu_table, title="Main Menu", border_style="blue"))
            
            sel = Prompt.ask("Option", choices=["1", "2", "3", "4"])
            
            if sel == '1':
                clear_screen()
                self._start_download()
                self._notify_end()
            elif sel == '2':
                clear_screen()
                self._retry_failed()
                self._notify_end()
            elif sel == '3':
                self._clear_cache()
            elif sel == '4':
                console.print("\n[magenta]Goodbye![/magenta]")
                break


if __name__ == '__main__':
    try:
        App().run()
    except KeyboardInterrupt:
        print("\n\n[!] Interrupted. Progress saved.")
        sys.exit(0)

