import json
import os
from dataclasses import dataclass


class QualityMode:
    HQ_ONLY = "HQ"
    MOBILE_ONLY = "MOB"
    BOTH = "ALL"


@dataclass
class Config:
    OUTPUT_FOLDER_HQ: str = "Audio_HQ"
    OUTPUT_FOLDER_MOBILE: str = "Audio_Mobile"
    INPUT_FOLDER: str = "Playlists"
    PROXIES_FILE: str = "proxies.txt"
    USE_PROXIES: bool = False

    ERROR_FILE: str = "Failed_songs.txt"
    ERROR_CSV: str = "Failed_songs.csv"
    CHECKPOINT_FILE: str = "progress.json"
    CACHE_FILE: str = "youtube_cache.json"
    COOKIES_FILE: str = "cookies.txt"
    CONFIG_FILE: str = "config.json"
    HISTORY_FILE: str = "history.json"
    M3U_FILE: str = "playlist.m3u"

    QUALITY_HQ_BITRATE: str = "320"
    QUALITY_MOBILE_BITRATE: str = "96"
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
    OUTPUT_FORMAT: str = "mp3"
    EMBED_LYRICS: bool = True

    # v7.0 - Spectral Analysis
    SPECTRAL_ANALYSIS: bool = True
    SPECTRAL_CUTOFF: int = 16000  # 16kHz typical for 128kbps

    @classmethod
    def load(cls, filepath: str = "config.json") -> "Config":
        """Carga configuracion desde archivo JSON"""
        cfg = cls()
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Mapear campos JSON a atributos
                mapping = {
                    "output_folder_hq": "OUTPUT_FOLDER_HQ",
                    "output_folder_mobile": "OUTPUT_FOLDER_MOBILE",
                    "quality_hq_bitrate": "QUALITY_HQ_BITRATE",
                    "quality_mobile_bitrate": "QUALITY_MOBILE_BITRATE",
                    "max_workers": "MAX_WORKERS",
                    "max_retries": "MAX_RETRIES",
                    "duration_tolerance": "DURATION_TOLERANCE",
                    "search_timeout": "SEARCH_TIMEOUT",
                    "cache_ttl_hours": "CACHE_TTL_HOURS",
                    "rate_limit_delay_min": "RATE_LIMIT_MIN",
                    "rate_limit_delay_max": "RATE_LIMIT_MAX",
                    "normalize_audio": "NORMALIZE_AUDIO",
                    "verify_md5": "VERIFY_MD5",
                    "generate_m3u": "GENERATE_M3U",
                    "save_history": "SAVE_HISTORY",
                    "debug_mode": "DEBUG_MODE",
                    "output_format": "OUTPUT_FORMAT",
                    "embed_lyrics": "EMBED_LYRICS",
                    "input_folder": "INPUT_FOLDER",
                    "proxies_file": "PROXIES_FILE",
                    "use_proxies": "USE_PROXIES",
                }
                for json_key, attr in mapping.items():
                    if json_key in data:
                        setattr(cfg, attr, data[json_key])
            except Exception:
                pass  # Usar valores por defecto si falla
        return cfg
