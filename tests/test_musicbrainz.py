import pytest
from unittest.mock import MagicMock, patch
from resonance_audio_builder.audio.musicbrainz import fetch_credits, get_composer_string, _fetch_work_composers

@pytest.fixture
def mock_response():
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {}
    return mock

def test_fetch_credits_empty_isrc():
    assert fetch_credits("") == {}

def test_fetch_credits_network_error(mock_response):
    with patch("resonance_audio_builder.audio.musicbrainz._rate_limited_get") as mock_get:
        mock_get.return_value.status_code = 500
        assert fetch_credits("US12345") == {}

def test_fetch_credits_no_recordings(mock_response):
    with patch("resonance_audio_builder.audio.musicbrainz._rate_limited_get") as mock_get:
        mock_get.return_value.json.return_value = {"recordings": []}
        assert fetch_credits("US12345") == {}

def test_fetch_credits_success():
    with patch("resonance_audio_builder.audio.musicbrainz._rate_limited_get") as mock_get:
        # 1. Search response
        mock_search = MagicMock()
        mock_search.status_code = 200
        mock_search.json.return_value = {
            "recordings": [{"id": "rec_id_1"}]
        }
        
        # 2. Detail response with artist relations
        mock_detail = MagicMock()
        mock_detail.status_code = 200
        mock_detail.json.return_value = {
            "relations": [
                {
                    "type": "composer",
                    "artist": {"name": "Mozart"}
                },
                {
                    "type": "producer",
                    "artist": {"name": "Dr. Dre"}
                },
                {
                    "type": "engineer",
                    "artist": {"name": "Engineer Guy"}
                },
                # Work relation
                {
                    "type": "performance",
                    "work": {"id": "work_id_1"}
                }
            ]
        }

        # 3. Work response
        mock_work = MagicMock()
        mock_work.status_code = 200
        mock_work.json.return_value = {
            "relations": [
                 {
                    "type": "writer",
                    "artist": {"name": "John Lenon"}
                }
            ]
        }
        
        mock_get.side_effect = [mock_search, mock_detail, mock_work]

        result = fetch_credits("US12345")
        
        assert "Mozart" in result["composers"]
        assert "John Lenon" in result["composers"]
        assert "Dr. Dre" in result["producers"]
        assert "Engineer Guy" in result["engineers"]

def test_get_composer_string():
    with patch("resonance_audio_builder.audio.musicbrainz.fetch_credits") as mock_fetch:
        mock_fetch.return_value = {"composers": ["A", "B"]}
        assert get_composer_string("ISRC") == "A, B"
        
        mock_fetch.return_value = {}
        assert get_composer_string("ISRC") is None

def test_fetch_work_composers_error():
    with patch("resonance_audio_builder.audio.musicbrainz._rate_limited_get") as mock_get:
        mock_get.side_effect = Exception("Network")
        assert _fetch_work_composers("wid", {}) == []

def test_fetch_credits_exception():
    with patch("resonance_audio_builder.audio.musicbrainz._rate_limited_get") as mock_get:
        mock_get.side_effect = Exception("Boom")
        assert fetch_credits("US123") == {}
