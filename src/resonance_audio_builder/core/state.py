import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Dict, List

from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.core.config import Config


@dataclass
class DownloadState:
    track_id: str
    artist: str
    title: str
    status: str
    bytes_total: int
    error: str
    timestamp: float


class ProgressDB:
    """Gestor de estado persistente usando SQLite"""

    def __init__(self, config: Config):
        self.cfg = config
        self.db_path = config.CHECKPOINT_FILE.replace(".json", ".db")
        self.lock = threading.RLock()
        self._init_db()

    def _init_db(self):
        """Inicializa esquema de la base de datos"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    track_id TEXT PRIMARY KEY,
                    artist TEXT,
                    title TEXT,
                    status TEXT,
                    bytes INTEGER DEFAULT 0,
                    error TEXT,
                    timestamp REAL,
                    retry_count INTEGER DEFAULT 0
                )
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON downloads(status)")
            conn.commit()
            conn.close()

    def mark(self, track: TrackMetadata, status: str, bytes_n: int = 0, error: str = None):
        """Registra progreso de una descarga"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            try:
                # Si es un error, incrementar retry_count
                if status == "error":
                    conn.execute(
                        """
                        INSERT INTO downloads (track_id, artist, title, status, bytes, error, timestamp, retry_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                        ON CONFLICT(track_id) DO UPDATE SET
                            status = excluded.status,
                            error = excluded.error,
                            timestamp = excluded.timestamp,
                            retry_count = retry_count + 1
                    """,
                        (track.track_id, track.artist, track.title, status, bytes_n, error, time.time()),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO downloads (track_id, artist, title, status, bytes, error, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(track_id) DO UPDATE SET
                            status = excluded.status,
                            bytes = bytes + excluded.bytes,
                            error = NULL,
                            timestamp = excluded.timestamp
                    """,
                        (track.track_id, track.artist, track.title, status, bytes_n, error, time.time()),
                    )

                conn.commit()
            finally:
                conn.close()

    def is_done(self, track_id: str) -> bool:
        """Verifica si una descarga está completada exitosamente"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT 1 FROM downloads WHERE track_id = ? AND status = 'ok'", (track_id,))
            exists = cursor.fetchone() is not None
            conn.close()
            return exists

    def get_stats(self) -> Dict[str, int]:
        """Retorna estadísticas de la sesión/base de datos"""
        stats = {"ok": 0, "skip": 0, "error": 0, "bytes": 0}
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            # Count by status
            cursor = conn.execute("SELECT status, COUNT(*), SUM(bytes) FROM downloads GROUP BY status")
            for row in cursor:
                status = row[0]
                count = row[1]
                total_bytes = row[2] or 0

                if status in stats:
                    stats[status] = count
                stats["bytes"] += total_bytes
            conn.close()
        return stats

    def get_failed_tracks(self, max_retries: int = 3) -> List[TrackMetadata]:
        """Obtiene lista de tracks fallidos que pueden reintentarse"""
        tracks = []
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                """
                SELECT artist, title, track_id, error FROM downloads
                WHERE status = 'error' AND retry_count < ?
            """,
                (max_retries,),
            )

            for row in cursor:
                # Reconstruir métadatos mínimos para reintento
                track = TrackMetadata(artist=row[0], title=row[1])
                tracks.append(track)
            conn.close()
        return tracks

    def clear(self):
        """Limpia la base de datos"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("DELETE FROM downloads")
            conn.commit()
            conn.close()
