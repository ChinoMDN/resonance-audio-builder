import pytest

from resonance_audio_builder.core.exceptions import (
    CopyrightError,
    DownloadError,
    DownloadTimeoutError,
    FatalError,
    GeoBlockError,
    NotFoundError,
    RateLimitError,
    RecoverableError,
    SearchError,
    TranscodeError,
    YouTubeError,
)


def test_exception_hierarchy_is_explicit():
    assert issubclass(RecoverableError, DownloadError)
    assert issubclass(FatalError, DownloadError)
    assert issubclass(SearchError, RecoverableError)
    assert issubclass(TranscodeError, RecoverableError)
    assert issubclass(DownloadTimeoutError, RecoverableError)
    assert issubclass(NotFoundError, FatalError)
    assert issubclass(CopyrightError, FatalError)
    assert issubclass(GeoBlockError, FatalError)
    assert issubclass(RateLimitError, RecoverableError)


@pytest.mark.parametrize(
    "message, expected_status, expected_type",
    [
        ("HTTP Error 429: Too Many Requests", 429, "RATE_LIMIT"),
        ("HTTP Error 403: Forbidden", 403, "FORBIDDEN"),
        ("Video blocked due to copyright claim", None, "COPYRIGHT"),
        ("This content is unavailable", None, "UNAVAILABLE"),
        ("Some random error", None, "UNKNOWN"),
    ],
)
def test_youtube_error_classification(message, expected_status, expected_type):
    err = YouTubeError(message)
    assert err.status_code == expected_status
    assert err.error_type == expected_type
    assert str(err) == message


def test_youtube_error_accepts_exception_instance():
    original = RuntimeError("HTTP Error 429: rate limit reached")
    err = YouTubeError(original)

    assert err.original_error is original
    assert err.status_code == 429
    assert err.error_type == "RATE_LIMIT"
