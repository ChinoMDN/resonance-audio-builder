from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from mutagen.mp4 import MP4

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

    def scan_library(
        self, hq_path: Path, mobile_path: Path = None, check_spectral: bool = False
    ) -> Dict[str, AuditResult]:
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
        files = list(folder_path.rglob("*.m4a"))
        result.total_files = len(files)

        for file_path in files:
            self._audit_single_file(file_path, result, check_spectral)

        return result

    def _audit_single_file(self, file_path: Path, result: AuditResult, check_spectral: bool) -> None:
        """Audit a single M4A file and update result."""
        try:
            result.total_size_bytes += file_path.stat().st_size
            self._check_file_tags(file_path, result)

            if check_spectral:
                self._check_spectral_integrity(file_path, result)

        except Exception as e:
            self.log.error(f"Error auditing {file_path}: {e}")
            result.errors.append(str(file_path))

    def _check_file_tags(self, file_path: Path, result: AuditResult) -> None:
        """Check M4A tags for metadata, cover, and lyrics."""
        try:
            audio = MP4(file_path)

            # Check title and artist (iTunes atoms)
            if "\xa9nam" not in audio or "\xa9ART" not in audio:
                result.missing_metadata.append(file_path.name)

            # Check cover art
            if "covr" not in audio:
                result.missing_covers.append(file_path.name)

            # Check lyrics
            if "\xa9lyr" not in audio:
                result.missing_lyrics.append(file_path.name)

        except Exception as e:
            self.log.debug(f"Metadata error on {file_path.name}: {e}")
            result.errors.append(f"{file_path.name}: Tag Error")

    def _check_spectral_integrity(self, file_path: Path, result: AuditResult) -> None:
        """Check if file is genuine HQ using spectral analysis."""
        if not self.analyzer.analyze_integrity(file_path):
            result.fake_hq_detected.append(file_path.name)
