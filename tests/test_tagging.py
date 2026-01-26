import pytest
from unittest.mock import MagicMock, patch
from resonance_audio_builder.audio.tagging import MetadataWriter
from resonance_audio_builder.audio.metadata import TrackMetadata

class TestMetadataWriter:
    @pytest.fixture
    def writer(self):
        logger = MagicMock()
        return MetadataWriter(logger)

    def test_write_metadata(self, writer, tmp_path):
        f = tmp_path / "test.mp3"
        f.write_bytes(b"dummy mp3")
        track = TrackMetadata(track_id="id1", title="Title", artist="Artist", album="Album")
        
        with patch.object(writer, "_load_audio") as mock_load:
            mock_load.return_value = MagicMock()
            with patch.object(writer, "_save_audio"):
                writer.write(f, track)
                assert mock_load.called

    def test_add_text_tags(self, writer):
        audio = MagicMock()
        track = TrackMetadata(track_id="id2", title="My Title", artist="My Artist", album="My Album")
        writer._add_text_tags(audio, track)
        
        # Check calls to audio.tags.add
        added_tags = [call.args[0].__class__.__name__ for call in audio.tags.add.call_args_list]
        assert "TIT2" in added_tags
        assert "TPE1" in added_tags
        assert "TALB" in added_tags

    def test_add_cover(self, writer):
        audio = MagicMock()
        track = TrackMetadata(track_id="id3", title="T", artist="A")
        track.cover_url = "http://example.com/image.jpg"
        
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.content = b"fake image"
            writer._add_cover(audio, track)
            assert audio.tags.add.called
            assert "APIC" in [call.args[0].__class__.__name__ for call in audio.tags.add.call_args_list]
