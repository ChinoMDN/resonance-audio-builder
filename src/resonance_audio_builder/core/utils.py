import hashlib
import json
import os
from pathlib import Path
from typing import List, Tuple


def calculate_md5(file_path: Path) -> str:
    """Calcula hash MD5 de un archivo"""
    hash_md5 = hashlib.md5(usedforsecurity=False)
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(131072), b""):  # 128KB chunks
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return ""


def export_m3u(tracks: List[Tuple[str, str, int]], filepath: str):
    """Exporta lista de canciones a formato M3U"""
    try:
        lines = ["#EXTM3U\n"]
        for path, title, duration in tracks:
            lines.append(f"#EXTINF:{duration},{title}\n{path}\n")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("".join(lines))
    except Exception:
        pass


def export_playlist_m3us(playlist_tracks_map: dict, output_folder: str):
    """
    Exporta archivos M3U individuales para cada playlist en la carpeta raíz de salida.

    Args:
        playlist_tracks_map: Dict mapping playlist_name -> List[TrackMetadata]
        output_folder: Carpeta base (ej: Audio_HQ)
    """
    try:

        for playlist_name, tracks in playlist_tracks_map.items():
            if not tracks:
                continue

            # El M3U se guarda en la raíz de la carpeta de salida (Audio_HQ/Playlist.m3u8)
            os.makedirs(output_folder, exist_ok=True)
            m3u_path = os.path.join(output_folder, f"{playlist_name}.m3u8")
            m3u_tracks = []

            for track in tracks:
                # Subcarpeta de descarga real (donde vive el archivo)
                subfolder = getattr(track, "playlist_subfolder", playlist_name)
                track_rel_folder = subfolder

                # Nombre del archivo esperado
                filename = f"{track.safe_filename}.m4a"
                rel_file_path = os.path.join(track_rel_folder, filename).replace(os.sep, "/")

                # Información para el M3U
                title = f"{track.artist} - {track.title}"
                duration = track.duration_seconds

                # Agregamos la entrada independientemente de si existe en disco
                # para que el M3U refleje el CSV completo.
                m3u_tracks.append((rel_file_path, title, duration))

            if m3u_tracks:
                export_m3u(m3u_tracks, m3u_path)
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
