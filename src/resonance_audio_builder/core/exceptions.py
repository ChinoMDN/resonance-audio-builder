"""Custom exception hierarchy for download error classification."""

import re


class DownloadError(Exception):
    """Error base de descarga"""


class RecoverableError(DownloadError):
    """Error recuperable - reintentar vale la pena"""


class FatalError(DownloadError):
    """Error fatal - no reintentar (copyright, geo-block, etc)"""


class SearchError(RecoverableError):
    """Error en búsqueda de YouTube"""


class TranscodeError(RecoverableError):
    """Error en transcodificación FFmpeg"""


class DownloadTimeoutError(RecoverableError):
    """Timeout en operación"""


class NotFoundError(FatalError):
    """Video no encontrado"""


class CopyrightError(FatalError):
    """Contenido bloqueado por copyright"""


class GeoBlockError(FatalError):
    """Contenido bloqueado por región"""


class YouTubeError(DownloadError):
    """Wrapper para errores de yt-dlp con clasificación inteligente"""

    def __init__(self, original_error: Exception | str):
        if isinstance(original_error, str):
            original_error = Exception(original_error)
        self.original_error = original_error
        self.status_code = self._extract_status(original_error)
        self.error_type = self._classify_error(original_error)
        super().__init__(str(original_error))

    def _extract_status(self, err: Exception) -> int | None:
        """Extract HTTP status code from error message."""
        match = re.search(r"HTTP Error (\d+)", str(err))
        if match:
            return int(match.group(1))
        return None

    def _classify_error(self, err: Exception) -> str:
        """Classify error type from error message."""
        err_str = str(err).lower()
        if self.status_code == 429 or "too many requests" in err_str:
            return "RATE_LIMIT"
        if self.status_code == 403 or "forbidden" in err_str:
            return "FORBIDDEN"
        if "copyright" in err_str:
            return "COPYRIGHT"
        if "unavailable" in err_str:
            return "UNAVAILABLE"
        return "UNKNOWN"


class RateLimitError(RecoverableError):
    """Error especifico para HTTP 429"""
