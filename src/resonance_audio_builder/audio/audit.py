import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any
from mutagen.id3 import ID3
from mutagen.mp3 import MP3

from resonance_audio_builder.audio.analysis import AudioAnalyzer
from resonance_audio_builder.core.logger import Logger

@dataclass
class AuditResult:
    total_files: int = 0
    total_size_bytes: int = 0
    missing_metadata: List[str] = field(default_factory=list)
    missing_covers: List[str] = field(default_factory=list)
    missing_lyrics: List[str] = field(default_factory=list)
    fake_hq_detected: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

class AudioAuditor:
    def __init__(self, logger: Logger, analyzer: AudioAnalyzer = None):
        self.log = logger
        self.analyzer = analyzer or AudioAnalyzer(logger)

    def scan_library(self, hq_path: Path, mobile_path: Path = None, check_spectral: bool = False) -> Dict[str, AuditResult]:
        results = {}
        
        if hq_path.exists():
            self.log.info(f"Auditing HQ Library: {hq_path}")
            results["HQ"] = self._audit_folder(hq_path, check_spectral=check_spectral)
            
        if mobile_path and mobile_path.exists():
            self.log.info(f"Auditing Mobile Library: {mobile_path}")
            results["Mobile"] = self._audit_folder(mobile_path, check_spectral=False)
            
        return results

    def _audit_folder(self, folder_path: Path, check_spectral: bool = False) -> AuditResult:
        result = AuditResult()
        
        # Get all mp3 files
        files = list(folder_path.rglob("*.mp3"))
        result.total_files = len(files)
        
        for file_path in files:
            try:
                # Size
                file_size = file_path.stat().st_size
                result.total_size_bytes += file_size
                
                # Tag Check
                try:
                    audio = MP3(file_path, ID3=ID3)
                    
                    # Metadata check
                    has_title = "TIT2" in audio
                    has_artist = "TPE1" in audio
                    if not has_title or not has_artist:
                        result.missing_metadata.append(file_path.name)
                        
                    # Cover check
                    has_cover = any(frame.startswith("APIC") for frame in audio.keys())
                    if not has_cover:
                        result.missing_covers.append(file_path.name)
                        
                    # Lyrics check
                    has_lyrics = any(frame.startswith("USLT") for frame in audio.keys())
                    if not has_lyrics:
                        result.missing_lyrics.append(file_path.name)
                        
                except Exception as e:
                    self.log.debug(f"Metadata error on {file_path.name}: {e}")
                    result.errors.append(f"{file_path.name}: Tag Error")

                # Spectral analysis
                if check_spectral:
                    is_genuine = self.analyzer.analyze_integrity(file_path)
                    if not is_genuine:
                        result.fake_hq_detected.append(file_path.name)
                        
            except Exception as e:
                self.log.error(f"Error auditing {file_path}: {e}")
                result.errors.append(str(file_path))
                
        return result
