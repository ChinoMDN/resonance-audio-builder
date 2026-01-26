import pytest
from unittest.mock import MagicMock, patch

from resonance_audio_builder.network.proxies import ProxyStats, SmartProxyManager


class TestProxyManagerFinal:
    def test_proxy_stats_tracking(self, tmp_path):
        """Test detailed stats tracking"""
        p_file = tmp_path / "proxies.txt"
        p_file.touch()

        mgr = SmartProxyManager(str(p_file), enabled=True)
        mgr.proxies = {"proxy1": ProxyStats(url="proxy1")}

        # Track multiple successes
        for _ in range(10):
            mgr.mark_success("proxy1")

        assert mgr.proxies["proxy1"].successes == 10

        # Track failures
        for _ in range(3):
            mgr.mark_failure("proxy1")

        assert mgr.proxies["proxy1"].failures == 3

    def test_get_requests_proxies_format(self, tmp_path):
        """Test proxy format for requests library (Using old wrapper for this one or Smart?)"""
        # Original ProxyManager wrapper exposes get_requests_proxies
        # So we can keep testing that class for THIS method, but use Smart for stats.
        p_file = tmp_path / "proxies.txt"
        p_file.touch()

        from resonance_audio_builder.network.proxies import ProxyManager

        mgr = ProxyManager(str(p_file), enabled=True)

        # Mock get_proxy
        mgr.get_proxy = MagicMock(return_value="http://proxy:8080")

        proxies = mgr.get_requests_proxies()

        assert proxies == {"http": "http://proxy:8080", "https": "http://proxy:8080"}
