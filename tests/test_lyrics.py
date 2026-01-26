from unittest.mock import patch

from resonance_audio_builder.audio.lyrics import fetch_lyrics


class TestLyrics:
    def test_fetch_lyrics_success(self):
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "syncedLyrics": "These are lyrics that are long enough to pass the length check of fifty characters."
            }
            res = fetch_lyrics("Artist", "Title", 180)
            assert res is not None

    def test_fetch_lyrics_not_found(self):
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 404
            res = fetch_lyrics("Artist", "Title", 180)
            assert res is None
