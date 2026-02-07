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


def export_playlist_m3us(playlist_tracks_map: dict, output_folder: str, playlists_base_folder: str = None):
    """
    Exporta archivos M3U individuales para cada playlist.
    El M3U se guarda junto con los archivos de la playlist.

    Args:
        playlist_tracks_map: Dict mapping playlist_name -> List[TrackMetadata]
        output_folder: Carpeta base donde están las subcarpetas de las playlists
        playlists_base_folder: No usado (mantenido por compatibilidad)
    """
    try:
        import os

        for playlist_name, tracks in playlist_tracks_map.items():
            if not tracks:
                continue

            # El M3U va junto con la carpeta de la playlist
            playlist_folder = os.path.join(output_folder, playlist_name)
            os.makedirs(playlist_folder, exist_ok=True)

            # Create M3U8 file inside the playlist folder (M3U8 = UTF-8 standard)
            m3u_path = os.path.join(playlist_folder, f"{playlist_name}.m3u8")
            m3u_tracks = []

            for track in tracks:
                # Look for the downloaded file - it may be in any playlist subfolder
                subfolder = getattr(track, "playlist_subfolder", playlist_name)
                track_folder = os.path.join(output_folder, subfolder)

                # Try to find the file
                filename = f"{track.safe_filename}.m4a"
                file_path = os.path.join(track_folder, filename)

                if os.path.exists(file_path):
                    # Use relative path from M3U location (the playlist folder)
                    rel_path = os.path.relpath(file_path, playlist_folder)
                    title = f"{track.artist} - {track.title}"
                    duration = track.duration_seconds
                    m3u_tracks.append((rel_path, title, duration))

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
