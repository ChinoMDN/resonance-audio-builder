from unittest.mock import MagicMock, patch

import pytest

from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.audio.youtube import YouTubeSearcher
from resonance_audio_builder.core.exceptions import NotFoundError


class TestYouTubeSearcher:
    @pytest.fixture
    def searcher(self, mock_youtube_api):
        # Patch yt_dlp.YoutubeDL at the import location in youtube.py
        mock_youtube_api.__enter__.return_value = mock_youtube_api

        with patch(
            "resonance_audio_builder.audio.youtube.yt_dlp.YoutubeDL",
            return_value=mock_youtube_api,
        ):
            # Ensure cache doesn't return mocks that act as True
            mock_cache = MagicMock()
            mock_cache.get.return_value = None

            searcher = YouTubeSearcher(MagicMock(), MagicMock(), mock_cache)
            yield searcher

    @pytest.mark.asyncio
    async def test_search_by_text_success(self, searcher, mock_youtube_api):
        """Standard search should return result"""
        mock_youtube_api.extract_info.return_value = {
            "entries": [{"id": "vid1", "title": "Song", "uploader": "Artist", "duration": 200, "webpage_url": "url"}]
        }
        track = TrackMetadata("id1", "Song", "Artist")
        res = await searcher.search(track)
        assert res.url == "url"
        assert res.title == "Song"

    @pytest.mark.asyncio
    async def test_search_not_found(self, searcher, mock_youtube_api):
        """Empty results should raise NotFoundError"""
        mock_youtube_api.extract_info.return_value = {"entries": []}
        track = TrackMetadata("id2", "Nonexistent", "Artist")
        with pytest.raises(NotFoundError):
            await searcher.search(track)

    @pytest.mark.asyncio
    async def test_search_excludes_covers(self, searcher, mock_youtube_api):
        """Should filter out covers by default"""
        mock_youtube_api.extract_info.return_value = {
            "entries": [
                {"id": "v1", "title": "Song (Cover by X)", "duration": 200, "webpage_url": "u1"},
                {"id": "v2", "title": "Song (Official)", "duration": 200, "webpage_url": "u2"},
            ]
        }
        track = TrackMetadata("id3", "Song", "Artist")
        res = await searcher.search(track)
        assert res.url == "u2"  # Should pick the non-cover

    @pytest.mark.asyncio
    async def test_search_cache_hit(self, searcher):
        """Second search should hit cache (mocking cache manager)"""
        searcher.app_cache.get.return_value = {"url": "cached_url", "title": "Cached", "duration": 100}

        track = TrackMetadata("id4", "Cached", "Artist")
        res = await searcher.search(track)
        assert res.url == "cached_url"
        assert res.cached is True

    @pytest.mark.asyncio
    async def test_search_network_error(self, searcher, mock_youtube_api):
        """Network error should be handled"""
        mock_youtube_api.extract_info.side_effect = Exception("Network Down")

        track = TrackMetadata("id5", "Query", "Artist")
        with pytest.raises(NotFoundError):
            await searcher.search(track)
