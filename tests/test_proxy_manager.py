from unittest.mock import AsyncMock, patch

import pytest

from resonance_audio_builder.network.proxies import SmartProxyManager


class TestProxyManager:
    @pytest.fixture
    def proxy_manager(self, mock_proxies, tmp_path):
        # Create a clean file for every test
        p_file = tmp_path / "proxies_test.txt"
        p_file.write_text("http://p1\nhttp://p2")
        return SmartProxyManager(str(p_file))

    def test_load_proxies(self, proxy_manager):
        """Should load proxies from file"""
        assert len(proxy_manager.proxies) == 2
        assert "http://p1" in proxy_manager.proxies

    def test_get_proxy_random_selection(self, proxy_manager):
        """Should return a proxy"""
        p = proxy_manager.get_proxy_sync()
        assert p in ["http://p1", "http://p2"]

    @pytest.mark.asyncio
    async def test_health_check_valid_proxy(self, proxy_manager):
        """Valid proxy should remain in list"""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b"google"
            mock_get.return_value.__aenter__.return_value = mock_resp

            # Use the internal _check_health method
            await proxy_manager._check_health(proxy_manager.proxies["http://p1"])
            assert proxy_manager.proxies["http://p1"].healthy is True

    def test_ban_after_threshold(self, proxy_manager):
        """Should ban proxy after failures"""
        proxy = "http://p1"
        # Need 6 failures to ban (> 5)
        for _ in range(6):
            proxy_manager.mark_failure(proxy)

        assert proxy_manager.proxies[proxy].healthy is False

    def test_disabled_returns_none(self):
        """Null file should act as disabled"""
        pm = SmartProxyManager("nonexistent.txt", enabled=False)
        assert pm.get_proxy_sync() is None
