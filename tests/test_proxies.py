import os
import pytest
from resonance_audio_builder.network.proxies import ProxyManager

@pytest.fixture
def proxy_file(tmp_path):
    p = tmp_path / "proxies.txt"
    p.write_text("http://1.1.1.1:8080\n# comment\nsocks5://2.2.2.2:1080\n")
    return str(p)

def test_proxy_loading(proxy_file):
    pm = ProxyManager(proxy_file, enabled=True)
    assert len(pm.proxies) == 2
    assert "http://1.1.1.1:8080" in pm.proxies
    assert "socks5://2.2.2.2:1080" in pm.proxies

def test_proxy_disabled(proxy_file):
    pm = ProxyManager(proxy_file, enabled=False)
    assert len(pm.proxies) == 0
    assert pm.get_proxy() is None

def test_get_proxy(proxy_file):
    pm = ProxyManager(proxy_file, enabled=True)
    proxy = pm.get_proxy()
    assert proxy in ["http://1.1.1.1:8080", "socks5://2.2.2.2:1080"]

def test_get_requests_proxies(proxy_file):
    pm = ProxyManager(proxy_file, enabled=True)
    proxies = pm.get_requests_proxies()
    assert "http" in proxies
    assert "https" in proxies
    assert proxies["http"] in ["http://1.1.1.1:8080", "socks5://2.2.2.2:1080"]

def test_missing_file():
    pm = ProxyManager("non_existent.txt", enabled=True)
    assert len(pm.proxies) == 0
