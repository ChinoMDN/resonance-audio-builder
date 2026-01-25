import asyncio
import os
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional

import aiohttp


@dataclass
class ProxyStats:
    url: str
    failures: int = 0
    successes: int = 0
    avg_latency: float = 0.0
    last_used: float = 0
    healthy: bool = True


class ProxyManager:
    """Legacy Proxy Manager (kept for interface compatibility if needed, but we'll try to replace usage)"""

    def __init__(self, proxies_file: str, enabled: bool = True):
        # Redirect to SmartProxyManager logic but sync
        self.smart = SmartProxyManager(proxies_file, enabled)

    def get_proxy(self) -> Optional[str]:
        return self.smart.get_proxy_sync()

    def get_requests_proxies(self) -> Dict[str, str]:
        p = self.get_proxy()
        return {"http": p, "https": p} if p else {}


class SmartProxyManager:
    """Manages proxy rotation with health checks and latency tracking."""

    def __init__(self, proxies_file: str, enabled: bool = True):
        self.proxies_file = proxies_file
        self.enabled = enabled
        self.proxies: Dict[str, ProxyStats] = {}
        self._load_proxies()
        self._health_check_interval = 300  # 5 min

    def _load_proxies(self):
        if not self.enabled or not os.path.exists(self.proxies_file):
            return

        try:
            with open(self.proxies_file, "r") as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith("#"):
                        self.proxies[url] = ProxyStats(url=url)
        except Exception as e:
            print(f"Error loading proxies: {e}")

    def get_proxy_sync(self) -> Optional[str]:
        """Synchronous best-effort selection (for legacy code)"""
        if not self.enabled or not self.proxies:
            return None

        # Filter mostly healthy
        candidates = [p for p in self.proxies.values() if p.healthy]
        if not candidates:
            # Fallback to all if everything fails (let application retry)
            candidates = list(self.proxies.values())

        return random.choice(candidates).url

    async def get_proxy_async(self) -> Optional[str]:
        """Smart async selection with optimistic fallback"""
        if not self.enabled or not self.proxies:
            return None

        healthy = [p for p in self.proxies.values() if p.healthy]

        # Optimistic: If no confirmed healthy, pick ANY and check in bg
        if not healthy:
            # Trigger check in background (don't await)
            asyncio.create_task(self._check_all())

            # Return random candidate to avoid blocking
            candidates = list(self.proxies.values())
            return random.choice(candidates).url if candidates else None

        # Weighted random selection
        weights = []
        for p in healthy:
            # Prefer higher success rate, lower latency
            score = (p.successes + 1) / (p.avg_latency + 0.1)
            weights.append(score)

        return random.choices(healthy, weights=weights, k=1)[0].url  # nosec B311

    async def _check_all(self):
        """Run health checks on a subset of proxies to avoid congestion"""
        # Shuffle and check first 20 to avoid launching 1000 tasks
        candidates = list(self.proxies.values())
        random.shuffle(candidates)
        subset = candidates[:20]

        tasks = [self._check_health(p) for p in subset]
        if tasks:
            await asyncio.gather(*tasks)

    async def _check_health(self, proxy: ProxyStats) -> bool:
        url = "https://www.youtube.com"  # Check target
        try:
            start = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.get(url, proxy=proxy.url, timeout=10) as resp:
                    latency = time.time() - start

                    # Update stats
                    proxy.avg_latency = (proxy.avg_latency * 0.7) + (latency * 0.3)
                    proxy.healthy = resp.status == 200

                    if proxy.healthy:
                        proxy.successes += 1
                    else:
                        proxy.failures += 1

                    return proxy.healthy
        except Exception:
            proxy.healthy = False
            proxy.failures += 1
            return False

    def mark_success(self, proxy_url: str):
        if proxy_url in self.proxies:
            self.proxies[proxy_url].successes += 1

    def mark_failure(self, proxy_url: str):
        if proxy_url in self.proxies:
            p = self.proxies[proxy_url]
            p.failures += 1
            if p.failures > 5:
                p.healthy = False
