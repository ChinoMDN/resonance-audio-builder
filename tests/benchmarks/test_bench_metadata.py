"""Benchmarks for CSV parsing and TrackMetadata construction."""

import csv
import io

import pytest

from resonance_audio_builder.audio.metadata import TrackMetadata

# Representative CSV row from a real Spotify export
SAMPLE_CSV_HEADER = (
    '"Track URI","Track Name","Artist URI(s)","Artist Name(s)",'
    '"Album URI","Album Name","Album Artist URI(s)","Album Artist Name(s)",'
    '"Album Release Date","Album Image URL","Disc Number","Track Number",'
    '"Track Duration (ms)","Track Preview URL","Explicit","Popularity",'
    '"ISRC","Added By","Added At"'
)

SAMPLE_CSV_ROW = (
    '"spotify:track:69kOkLUCkxIZYexIgSG8rq",'
    '"Get Lucky (feat. Pharrell Williams and Nile Rodgers)",'
    '"spotify:artist:4tZwfgrHOc3mvqYlEYSvVi, spotify:artist:2RdwBSPQiwcmiDo9kixcl8",'
    '"Daft Punk, Pharrell Williams",'
    '"spotify:album:4m2880jivSbbyEGAKfITCa","Random Access Memories",'
    '"spotify:artist:4tZwfgrHOc3mvqYlEYSvVi","Daft Punk",'
    '"2013-05-20","https://i.scdn.co/image/ab67616d0000b2739b9b36b0e22870b9f542d937",'
    '"1","8","369626",'
    '"https://p.scdn.co/mp3-preview/6de52dda0d37a0646987856c3b9f7da075d965b4",'
    '"false","75","USQX91300108","","2026-02-21T18:48:24Z"'
)


def _parse_row() -> dict:
    """Parse a single CSV row into a dict."""
    text = f"{SAMPLE_CSV_HEADER}\n{SAMPLE_CSV_ROW}"
    reader = csv.DictReader(io.StringIO(text))
    return next(reader)


@pytest.fixture
def csv_row():
    """Pre-parsed CSV row for benchmarks that only test TrackMetadata."""
    return _parse_row()


class TestCSVParsingBenchmarks:
    """Benchmarks for CSV row parsing into TrackMetadata."""

    def test_csv_row_parsing(self, benchmark):
        """Benchmark: Parse a raw CSV line into a dict."""
        benchmark(_parse_row)

    def test_track_metadata_from_csv_row(self, benchmark, csv_row):
        """Benchmark: Construct TrackMetadata from a pre-parsed CSV row."""
        benchmark(TrackMetadata.from_csv_row, csv_row)

    def test_full_parse_pipeline(self, benchmark):
        """Benchmark: Full pipeline — CSV text → dict → TrackMetadata."""

        def full_pipeline():
            row = _parse_row()
            return TrackMetadata.from_csv_row(row)

        benchmark(full_pipeline)


class TestTrackMetadataPropertyBenchmarks:
    """Benchmarks for TrackMetadata property accessors."""

    @pytest.fixture
    def track(self, csv_row):
        return TrackMetadata.from_csv_row(csv_row)

    def test_artists_property(self, benchmark, track):
        """Benchmark: Parse multi-artist string into list."""
        benchmark(lambda: track.artists)

    def test_genre_list_property(self, benchmark):
        """Benchmark: Parse genre string into list."""
        track = TrackMetadata(
            track_id="test",
            title="Test",
            artist="Test",
            genres="Electronic, Dance, House, Synthpop, Nu-Disco, French House",
        )
        benchmark(lambda: track.genre_list)

    def test_duration_seconds(self, benchmark, track):
        """Benchmark: Compute duration in seconds."""
        benchmark(lambda: track.duration_seconds)

    def test_safe_filename(self, benchmark, track):
        """Benchmark: Generate safe filename from track metadata."""
        benchmark(lambda: track.safe_filename)


class TestBatchParsingBenchmarks:
    """Benchmarks simulating batch CSV processing (playlist-scale)."""

    def test_parse_25_tracks(self, benchmark, csv_row):
        """Benchmark: Parse 25 tracks (typical small playlist)."""

        def parse_batch():
            return [TrackMetadata.from_csv_row(csv_row) for _ in range(25)]

        benchmark(parse_batch)

    def test_parse_100_tracks(self, benchmark, csv_row):
        """Benchmark: Parse 100 tracks (typical large playlist)."""

        def parse_batch():
            return [TrackMetadata.from_csv_row(csv_row) for _ in range(100)]

        benchmark(parse_batch)
