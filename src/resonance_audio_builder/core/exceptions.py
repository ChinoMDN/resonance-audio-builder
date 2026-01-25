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


class YouTubeError(DownloadError):
    """Wrapper para errores de yt-dlp con clasificación inteligente"""
    def __init__(self, original_error: Exception):
        self.original_error = original_error
        self.status_code = self._extract_status(original_error)
        self.error_type = self._classify_error(original_error)
        super().__init__(str(original_error))
    
    def _extract_status(self, err: Exception) -> int | None:
        import re
        # Busca patrones como "HTTP Error 429"
        match = re.search(r'HTTP Error (\d+)', str(err))
        if match:
            return int(match.group(1))
        return None
    
    def _classify_error(self, err: Exception) -> str:
        err_str = str(err).lower()
        if self.status_code == 429 or "too many requests" in err_str:
            return "RATE_LIMIT"
        elif self.status_code == 403 or "forbidden" in err_str:
            return "FORBIDDEN"
        elif "copyright" in err_str:
            return "COPYRIGHT"
        elif "unavailable" in err_str:
            return "UNAVAILABLE"
        return "UNKNOWN"


class RateLimitError(RecoverableError):
    """Error especifico para HTTP 429"""
    pass
