from resonance_audio_builder.network.utils import get_random_user_agent, is_valid_ip


def test_get_random_user_agent():
    ua = get_random_user_agent()
    assert isinstance(ua, str)
    assert len(ua) > 10


def test_is_valid_ip():
    assert is_valid_ip("1.2.3.4") is True
    assert is_valid_ip("256.0.0.1") is False
    assert is_valid_ip("abcd") is False
    assert is_valid_ip("1.2.3") is False
