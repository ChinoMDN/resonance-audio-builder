import sqlite3
import threading
import time


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
                self.cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cache (
                        key TEXT PRIMARY KEY,
                        url TEXT,
                        title TEXT,
                        duration INTEGER,
                        timestamp REAL
                    )
                """
                )
                self.conn.commit()
            except Exception as e:
                print(f"[!] Cache DB Init Error: {e}")

    def get(self, key: str, ttl_hours: int):
        if not hasattr(self, "cursor"):
            return None
        limit_time = time.time() - (ttl_hours * 3600)
        with self.lock:
            try:
                self.cursor.execute(
                    "SELECT url, title, duration FROM cache WHERE key = ? AND timestamp > ?", (key, limit_time)
                )
                row = self.cursor.fetchone()
                if row:
                    return {"url": row[0], "title": row[1], "duration": row[2]}
            except Exception:
                pass
            return None

    def set(self, key: str, data: dict):
        if not hasattr(self, "cursor"):
            return
        with self.lock:
            try:
                self.cursor.execute(
                    """
                    INSERT OR REPLACE INTO cache (key, url, title, duration, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (key, data["url"], data["title"], data.get("duration", 0), time.time()),
                )
                self.conn.commit()
            except Exception:
                pass

    def clear(self):
        if not hasattr(self, "cursor"):
            return
        # Use acquire with timeout to prevent deadlock
        acquired = self.lock.acquire(timeout=5)
        if not acquired:
            return
        try:
            self.cursor.execute("DELETE FROM cache")
            self.conn.commit()
        except Exception:
            pass
        finally:
            self.lock.release()

    def count(self) -> int:
        if not hasattr(self, "cursor"):
            return 0
        with self.lock:
            try:
                self.cursor.execute("SELECT COUNT(*) FROM cache")
                return self.cursor.fetchone()[0]
            except Exception:
                return 0

    def __del__(self):
        """Cleanup: close connection when object is destroyed"""
        if hasattr(self, "conn"):
            try:
                self.conn.close()
            except Exception:
                pass

    def close(self):
        """Explicit close method"""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        """Context manager support"""
        return self

    def __exit__(self, *args):
        """Context manager cleanup"""
        self.close()
