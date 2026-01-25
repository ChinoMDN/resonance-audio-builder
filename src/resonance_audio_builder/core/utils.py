import hashlib
import json
import os
from pathlib import Path
from typing import List, Tuple


def calculate_md5(file_path: Path) -> str:
    """Calcula hash MD5 de un archivo"""
    hash_md5 = hashlib.md5()  # nosec B324
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return ""


def export_m3u(tracks: List[Tuple[str, str, int]], filepath: str):
    """Exporta lista de canciones a formato M3U"""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for path, title, duration in tracks:
                f.write(f"#EXTINF:{duration},{title}\n")
                f.write(f"{path}\n")
    except Exception:
        pass


def save_history(history_file: str, session_data: dict):
    """Guarda historial de sesion"""
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    history.append(session_data)

    # Mantener solo ultimas 50 sesiones
    if len(history) > 50:
        history = history[-50:]

    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
