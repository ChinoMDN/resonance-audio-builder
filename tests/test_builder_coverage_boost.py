from unittest.mock import patch

from resonance_audio_builder.core.builder import App


class TestBuilderCoverageBoost:
    def test_read_csv_malformed(self, tmp_path):
        """Test handling of malformed CSV"""
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("Not,Valid,CSV\n\x00\x00\x00", encoding="utf-8")

        # Mock dependencies to avoid real init
        with (
            patch("resonance_audio_builder.core.builder.ProgressDB"),
            patch("resonance_audio_builder.core.builder.CacheManager"),
        ):
            app = App()
            rows = app._read_csv(str(csv_file))
            assert rows == []

    def test_clear_cache_all(self, tmp_path):
        """Test clearing all data"""
        with (
            patch("resonance_audio_builder.core.builder.ProgressDB"),
            patch("resonance_audio_builder.core.builder.CacheManager"),
        ):
            app = App()

            # Create dummy files
            # Check where clear_cache looks for files.
            # builder.py: "cache.db", self.cfg.CACHE_FILE
            # We need to ensure we are in a dir where we can create these, OR patch os.remove/exists

            with patch("os.path.exists", return_value=True), patch("os.remove") as mock_remove:

                with patch("resonance_audio_builder.core.builder.Prompt.ask", return_value="3"):  # Clear all
                    app._clear_cache()

                # Should attempt to remove cache.db, CACHE_FILE, and temp files
                assert mock_remove.called

    def test_retry_failed_with_errors(self, tmp_path):
        """Test retry flow with actual failed songs"""
        with (
            patch("resonance_audio_builder.core.builder.ProgressDB"),
            patch("resonance_audio_builder.core.builder.CacheManager"),
        ):
            app = App()

            # Create Failed_songs.csv
            failed_csv = tmp_path / "Failed_songs.csv"
            failed_csv.write_text("Artist,Title\nFailed,Song", encoding="utf-8")

            with patch.object(app.cfg, "ERROR_CSV", str(failed_csv)):
                with (
                    patch.object(app, "_select_quality"),
                    patch("resonance_audio_builder.core.builder.DownloadManager") as mock_mgr_cls,
                    patch("resonance_audio_builder.core.builder.asyncio.run"),
                ):

                    # Need to mock console/input interaction?
                    # _retry_failed calls console.print, etc.
                    # It also does async run.

                    with patch("builtins.input"):  # For "Enterprise para continuar..."
                        app._retry_failed()

                        assert mock_mgr_cls.called
