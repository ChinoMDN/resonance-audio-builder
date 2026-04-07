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

    # ── ISRC lookup tests ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_isrc_lookup_returns_match(self, searcher, mock_youtube_api):
        """ISRC search should find the exact song with matching duration"""
        mock_youtube_api.extract_info.return_value = {
            "entries": [{"title": "Lee - Rain", "duration": 229, "webpage_url": "https://yt/isrc_hit"}]
        }
        track = TrackMetadata("id_isrc", "Rain", "Lee", isrc="KRMIM2006387", duration_ms=229090)
        res = await searcher.search(track)
        assert res.url == "https://yt/isrc_hit"

    @pytest.mark.asyncio
    async def test_isrc_lookup_rejects_bad_duration(self, searcher, mock_youtube_api):
        """ISRC match with wildly different duration should be rejected"""
        # First call: ISRC lookup returns wrong duration
        # Subsequent calls: text search returns nothing
        mock_youtube_api.extract_info.return_value = {
            "entries": [{"title": "Wrong Song", "duration": 500, "webpage_url": "https://yt/wrong"}]
        }
        track = TrackMetadata("id_dur", "Rain", "Lee", isrc="KRMIM2006387", duration_ms=229090)
        with pytest.raises(NotFoundError):
            await searcher.search(track)

    # ── Query cleaning tests ────────────────────────────────────────

    def test_clean_query_title_removes_feat(self, searcher):
        """Should strip (feat. ...) from Spotify titles"""
        assert searcher._clean_query_title("Bad Guy (feat. Justin Bieber)") == "Bad Guy"

    def test_clean_query_title_removes_remastered(self, searcher):
        """Should strip - Remastered XXXX suffixes"""
        assert searcher._clean_query_title("Song Title - Remastered 2023") == "Song Title"

    def test_clean_query_title_preserves_normal(self, searcher):
        """Should not modify titles without Spotify suffixes"""
        assert searcher._clean_query_title("Alma Enamorada") == "Alma Enamorada"

    def test_clean_query_title_removes_from_quotes(self, searcher):
        """Should strip (From 'Movie Name') suffixes"""
        result = searcher._clean_query_title('I Love You So (From "Junko Ohashi")')
        assert result == "I Love You So"

    # ── Short artist detection ──────────────────────────────────────

    def test_is_short_artist_detects_generic(self, searcher):
        """Single-word artist names should be flagged"""
        track = TrackMetadata("id", "Rain", "Lee")
        assert searcher._is_short_artist(track) is True

    def test_is_short_artist_allows_long_names(self, searcher):
        """Multi-word artist names should not be flagged"""
        track = TrackMetadata("id", "Song", "Ariel Camacho y Los Plebes Del Rancho")
        assert searcher._is_short_artist(track) is False

    # ── Score threshold tests ───────────────────────────────────────

    @pytest.mark.asyncio
    async def test_low_score_rejected(self, searcher, mock_youtube_api):
        """Results with very low scores should be rejected as not found"""
        mock_youtube_api.extract_info.return_value = {
            "entries": [
                {
                    "title": "Completely Unrelated Video About Cooking",
                    "duration": 600,
                    "webpage_url": "https://yt/wrong",
                    "uploader": "CookingChannel",
                    "channel": "CookingChannel",
                }
            ]
        }
        track = TrackMetadata("id_low", "Horrible", "Vete a la Versh", duration_ms=221423)
        with pytest.raises(NotFoundError):
            await searcher.search(track)

    # ── Collaborative artist tests ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_collaborative_artist_matching(self, searcher, mock_youtube_api):
        """Should match when at least one collaborative artist appears"""
        mock_youtube_api.extract_info.return_value = {
            "entries": [
                {
                    "title": "Alma Enamorada - Chalino Sanchez",
                    "duration": 176,
                    "webpage_url": "https://yt/chalino",
                    "uploader": "Chalino Sanchez - Topic",
                    "channel": "Chalino Sanchez - Topic",
                }
            ]
        }
        track = TrackMetadata(
            "id_collab", "Alma Enamorada", "Chalino Sanchez, Los Amables Del Norte", duration_ms=175891
        )
        res = await searcher.search(track)
        assert res.url == "https://yt/chalino"

    # ── Parenthetical noise filtering ───────────────────────────────

    def test_strip_parenthetical_tokens(self, searcher):
        """Tokens inside parentheses not in query should be excluded"""
        tokens = searcher._strip_parenthetical_tokens("Song Title (Official Music Video)", "Song Title Audio")
        assert "official" not in tokens
        assert "music" not in tokens
        assert "video" not in tokens
        assert "song" in tokens
        assert "title" in tokens


class TestScoringEdgeCases:
    """Test scoring logic for the problematic tracks from erroneas.csv"""

    @pytest.fixture
    def searcher(self):
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        config = MagicMock()
        config.COOKIES_FILE = "nonexistent.txt"
        config.SEARCH_TIMEOUT = 30
        config.MAX_CONCURRENT_SEARCHES = 1
        return YouTubeSearcher(config, MagicMock(), mock_cache)

    def test_topic_bonus_artist_match(self, searcher):
        """Topic channel matching the artist should get higher bonus"""
        entry = {
            "title": "Rain",
            "duration": 229,
            "uploader": "Lee - Topic",
            "channel": "Lee - Topic",
        }
        track = TrackMetadata("id", "Rain", "Lee", duration_ms=229090)
        score = searcher._score_entry(entry, "Lee - Rain Audio", track)
        assert score > 0  # Should be positive with matching Topic

    def test_topic_bonus_artist_mismatch(self, searcher):
        """Topic channel NOT matching the artist should get low bonus"""
        entry = {
            "title": "Rain",
            "duration": 229,
            "uploader": "OtherArtist - Topic",
            "channel": "OtherArtist - Topic",
        }
        track = TrackMetadata("id", "Rain", "Lee", duration_ms=229090)
        score = searcher._score_entry(entry, "Lee - Rain Audio", track)

        # Compare with artist-matched Topic
        entry_match = {
            "title": "Rain",
            "duration": 229,
            "uploader": "Lee - Topic",
            "channel": "Lee - Topic",
        }
        score_match = searcher._score_entry(entry_match, "Lee - Rain Audio", track)
        assert score_match > score  # Artist-matched Topic should score higher

    def test_wrong_artist_gets_negative_inf(self, searcher):
        """Video from completely wrong artist should be discarded"""
        entry = {
            "title": "Rain - Bruce Lee Documentary",
            "duration": 3600,
            "uploader": "HistoryChannel",
            "channel": "HistoryChannel",
        }
        track = TrackMetadata("id", "Rain", "Lee", duration_ms=229090)
        score = searcher._score_entry(entry, "Lee - Rain Audio", track)
        # Should be below MIN_SCORE_THRESHOLD so it gets rejected
        assert score < YouTubeSearcher.MIN_SCORE_THRESHOLD

    def test_version_penalty_lyrics(self, searcher):
        """Lyrics version should get penalized"""
        entry_original = {
            "title": "Horrible - Vete a la Versh",
            "duration": 221,
            "uploader": "Vete a la Versh",
            "channel": "Vete a la Versh",
        }
        entry_lyrics = {
            "title": "Horrible - Vete a la Versh (Lyrics)",
            "duration": 221,
            "uploader": "LyricsChannel",
            "channel": "LyricsChannel",
        }
        track = TrackMetadata("id", "Horrible", "Vete a la Versh", duration_ms=221423)
        query = "Vete a la Versh - Horrible Audio"

        score_orig = searcher._score_entry(entry_original, query, track)
        score_lyrics = searcher._score_entry(entry_lyrics, query, track)
        assert score_orig > score_lyrics

    def test_expanded_hard_excludes(self, searcher):
        """Mashup and tutorial should be excluded"""
        entry = {
            "title": "Song Mashup Collection",
            "duration": 200,
            "uploader": "SomeChannel",
            "channel": "SomeChannel",
        }
        track = TrackMetadata("id", "Song", "Artist", duration_ms=200000)
        score = searcher._score_entry(entry, "Artist - Song Audio", track)
        assert score == float("-inf")
