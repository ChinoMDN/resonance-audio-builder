from unittest.mock import MagicMock, patch

import pytest
from mutagen.mp4 import MP4Cover

from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.audio.tagging import MetadataWriter


class TestMetadataWriter:
    @pytest.fixture
    def writer(self):
        logger = MagicMock()
        return MetadataWriter(logger)

    def test_write_metadata_basic(self, writer, tmp_path):
        f = tmp_path / "test.m4a"
        f.touch()
        track = TrackMetadata(track_id="id1", title="Title", artist="Artist", album="Album")

        with patch("resonance_audio_builder.audio.tagging.MP4") as mock_mp4:
            mock_audio = MagicMock()
            mock_mp4.return_value = mock_audio
            # Mock dictionary behavior
            mock_audio.__setitem__ = MagicMock()

            writer.write(f, track)

            # verify save called
            mock_audio.save.assert_called()

            # verify basic tags
            calls = mock_audio.__setitem__.call_args_list
            keys_set = [c[0][0] for c in calls]
            assert "\xa9nam" in keys_set
            assert "\xa9ART" in keys_set
            assert "\xa9alb" in keys_set

    def test_embed_cover(self, writer, tmp_path):
        f = tmp_path / "test.m4a"
        f.touch()
        track = TrackMetadata(track_id="id3", title="T", artist="A")
        # Simulate header for JPEG
        track.cover_data = b"\xff\xd8\xff\xe0"

        with patch("resonance_audio_builder.audio.tagging.MP4") as mock_mp4:
            mock_audio = MagicMock()
            mock_mp4.return_value = mock_audio
            mock_audio.__setitem__ = MagicMock()

            writer.write(f, track)

            # verify cover set
            calls = mock_audio.__setitem__.call_args_list
            keys_set = [c[0][0] for c in calls]
            assert "covr" in keys_set

            # Verify the value passed to covr is correct type
            # Find the call for 'covr'
            covr_call = next(c for c in calls if c[0][0] == "covr")
            val = covr_call[0][1]
            assert isinstance(val, list)
            assert isinstance(val[0], MP4Cover)
            assert val[0].imageformat == MP4Cover.FORMAT_JPEG

    def test_embed_cover_png(self, writer, tmp_path):
        f = tmp_path / "test.m4a"
        f.touch()
        track = TrackMetadata(track_id="id4", title="T", artist="A")
        # Simulate header for PNG
        track.cover_data = b"\x89PNG\r\n\x1a\n"

        with patch("resonance_audio_builder.audio.tagging.MP4") as mock_mp4:
            mock_audio = MagicMock()
            mock_mp4.return_value = mock_audio
            mock_audio.__setitem__ = MagicMock()

            writer.write(f, track)

            # Check for PNG format
            calls = mock_audio.__setitem__.call_args_list
            covr_call = next(c for c in calls if c[0][0] == "covr")
            val = covr_call[0][1]
            assert val[0].imageformat == MP4Cover.FORMAT_PNG

    def test_write_extended_metadata(self, writer, tmp_path):
        f = tmp_path / "extended.m4a"
        f.touch()
        track = TrackMetadata(
            track_id="id_ext", title="Extended", artist="Artist", isrc="US1234567890", added_by="UserX", popularity=50
        )

        # Mock fetch_credits to verify enrichment
        with (
            patch("resonance_audio_builder.audio.tagging.fetch_credits") as mock_fetch,
            patch("resonance_audio_builder.audio.tagging.MP4") as mock_mp4,
        ):

            mock_fetch.return_value = {"composers": ["Mozart"], "producers": ["Dr. Dre"], "engineers": []}

            mock_audio = MagicMock()
            mock_mp4.return_value = mock_audio

            # Capture writes to a real dict because MagicMock calls are hard to check for specific key/value pairs
            store = {}

            def setitem(key, val):
                store[key] = val

            mock_audio.__setitem__.side_effect = setitem

            writer.write(f, track)

            # Verify enrichment called
            mock_fetch.assert_called_with("US1234567890")
            # Track object should be updated in place
            assert track.composers == ["Mozart"]

            # Verify standard atom (Composer)
            assert store.get("\xa9wrt") == "Mozart"

            # Verify freeform atoms
            # Note: In code we set them as lists of bytes: [b"value"]

            assert store.get("----:com.apple.iTunes:ISRC") == [b"US1234567890"]
            assert store.get("----:com.apple.iTunes:ADDED_BY") == [b"UserX"]
            assert store.get("----:com.apple.iTunes:SPOTIFY_POPULARITY") == [b"50"]

            # Verify Producer (from enrichment)
            assert store.get("----:com.apple.iTunes:PRODUCER") == [b"Dr. Dre"]

    def test_track_metadata_from_csv_extended(self):
        # Sample row provided by user
        row = {
            "Track URI": "spotify:track:0lqol9oGXUf7o7zv48x7u1",
            "Track Name": "Beanie",
            "Artist Name(s)": "Chezile",
            "Album Name": "47",
            "Album Artist Name(s)": "Chezile",
            "Album Release Date": "2024-02-27",
            "Image URL": "https://i.scdn.co/image/...",
            "Track Number": "5",
            "Disc Number": "1",
            "Track Duration (ms)": "132160",
            "Explicit": "false",
            "Popularity": "51",
            "ISRC": "QZWFH2353145",
            "Added By": "spotify:user:31j4p3myumlbf3zh74ryxk36j5f4",
            "Added At": "2025-04-19T09:37:47Z",
            "Artist Genres": "",
            "Danceability": "0.531",
            "Energy": "0.556",
            "Key": "5",
            "Loudness": "-6.245",
            "Mode": "1",
            "Speechiness": "0.0252",
            "Acousticness": "0.407",
            "Instrumentalness": "0.00915",
            "Liveness": "0.318",
            "Valence": "0.156",
            "Tempo": "138.978",
            "Time Signature": "3",
            "Label": "Chezile / 10K Projects",
            "Copyrights": "C © 2024 Chezile",
        }

        t = TrackMetadata.from_csv_row(row)

        assert t.title == "Beanie"
        assert t.artist == "Chezile"
        assert t.isrc == "QZWFH2353145"
        assert t.added_by == "spotify:user:31j4p3myumlbf3zh74ryxk36j5f4"
        assert t.added_at == "2025-04-19T09:37:47Z"
        assert t.popularity == 51
        assert t.energy == 0.556
        assert t.tempo == 138.978
        assert t.label == "Chezile / 10K Projects"
        assert t.copyrights == "C © 2024 Chezile"
