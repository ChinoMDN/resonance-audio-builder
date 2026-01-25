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
