# import os (removed)

import pytest

from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.core.config import Config
from resonance_audio_builder.core.state import ProgressDB


class TestProgressDB:
    @pytest.fixture
    def db(self, tmp_path):
        cfg = Config()
        cfg.CHECKPOINT_FILE = str(tmp_path / "progress.json")
        return ProgressDB(cfg)

    def test_mark_and_get_stats(self, db):
        t1 = TrackMetadata(track_id="track1", title="Title 1", artist="Artist 1")
        t2 = TrackMetadata(track_id="track2", title="Title 2", artist="Artist 2")
        t3 = TrackMetadata(track_id="track3", title="Title 3", artist="Artist 3")

        db.mark(t1, "ok")
        db.mark(t2, "error")
        db.mark(t3, "skip")

        stats = db.get_stats()
        assert stats["ok"] == 1
        assert stats["error"] == 1
        assert stats["skip"] == 1
        # Total is not explicitly in stats dict, but we can sum if needed
        # stats = {"ok": 1, "skip": 1, "error": 1, "bytes": 0}
        assert sum(v for k, v in stats.items() if k != "bytes") == 3

    def test_is_done(self, db):
        track = TrackMetadata(track_id="1", title="T", artist="A")
        db.mark(track, "ok")
        assert db.is_done(track.track_id) is True

        # Non-existent track
        t2 = TrackMetadata(track_id="2", title="T2", artist="A2")
        assert db.is_done(t2.track_id) is False
        assert db.is_done("track2") is False

    def test_persistence(self, tmp_path):
        checkpoint = str(tmp_path / "persist.json")
        cfg = Config()
        cfg.CHECKPOINT_FILE = checkpoint

        db1 = ProgressDB(cfg)
        t1 = TrackMetadata(track_id="track1", title="Title 1", artist="Artist 1")
        db1.mark(t1, "ok")

        db2 = ProgressDB(cfg)
        assert db2.is_done("track1") is True
