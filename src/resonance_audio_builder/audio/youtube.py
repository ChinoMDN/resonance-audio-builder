import os
import random
import time
import asyncio
import json
from dataclasses import dataclass
from typing import Dict, Optional, Any

import yt_dlp

from resonance_audio_builder.core.config import Config
from resonance_audio_builder.core.logger import Logger
from resonance_audio_builder.core.exceptions import NotFoundError, YouTubeError
from resonance_audio_builder.network.cache import CacheManager
from resonance_audio_builder.network.utils import USER_AGENTS, validate_cookies_file
from resonance_audio_builder.network.proxies import SmartProxyManager
from resonance_audio_builder.audio.metadata import TrackMetadata

@dataclass
class SearchResult:
    url: str
    title: str
    duration: int
    cached: bool = False

class YouTubeSearcher:
    def __init__(self, config: Config, logger: Logger, cache_manager: CacheManager, proxy_manager: SmartProxyManager = None):
        self.cfg = config
        self.log = logger
        self.app_cache = cache_manager
        self.proxy_manager = proxy_manager
        self.cache: Dict[str, dict] = {}
        self._cookies_valid = validate_cookies_file(config.COOKIES_FILE)
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cfg.CACHE_FILE):
            try:
                with open(self.cfg.CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    now = time.time()
                    ttl = self.cfg.CACHE_TTL_HOURS * 3600
                    self.cache = {k: v for k, v in data.items() if now - v.get("_ts", 0) < ttl}
                    self.log.debug(f"Caché cargado: {len(self.cache)} entradas")
            except Exception as e:
                self.log.debug(f"Error cargando caché: {e}")

    async def search(self, track: TrackMetadata, attempt: int = 1) -> SearchResult:
        """Async search implementation"""
        # 1. Check ISRC Cache
        if track.isrc:
            if self.app_cache:
                cached = self.app_cache.get(f"isrc_{track.isrc}", ttl_hours=24 * 30)
                if cached:
                    self.log.debug(f"Cache hit (ISRC): {track.title}")
                    return SearchResult(cached["url"], cached["title"], cached["duration"], cached=True)

            result = await self._lookup(f"isrc_{track.isrc}", f'"{track.isrc}"', track.duration_seconds)
            if result:
                return result

        # 2. Check Text Cache
        query = f"{track.artist} - {track.title} Audio"
        cache_key = query.lower().strip()[:100]

        if self.app_cache:
            cached = self.app_cache.get(cache_key, ttl_hours=24 * 7)
            if cached:
                self.log.debug(f"Cache hit: {track.title}")
                return SearchResult(cached["url"], cached["title"], cached["duration"], cached=True)

        # 3. Lookup Text
        result = await self._lookup(cache_key, query, track.duration_seconds)
        if result:
            return result

        # 4. Retry with alternate query if needed
        if attempt < 2:
            query_alt = f"{track.artist} {track.title} Topic"
            result = await self._lookup(query_alt.lower()[:100], query_alt, track.duration_seconds)
            if result:
                return result

        raise NotFoundError(f"No encontrado: {track.artist} - {track.title}")

    async def _lookup(self, cache_key: str, query: str, duration: int) -> Optional[SearchResult]:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "noplaylist": True,
            "socket_timeout": self.cfg.SEARCH_TIMEOUT,
            "http_headers": {"User-Agent": random.choice(USER_AGENTS)},
        }
        
        # Get proxy asynchronously
        if self.proxy_manager:
            proxy = await self.proxy_manager.get_proxy_async()
            if proxy:
                opts["proxy"] = proxy

        if self._cookies_valid:
            opts["cookiefile"] = self.cfg.COOKIES_FILE

        try:
            # Run blocking yt-dlp in executor
            loop = asyncio.get_running_loop()
            
            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(f"ytsearch5:{query}", download=False)
            
            # Using default thread executor
            results = await loop.run_in_executor(None, _extract)

            if not results or "entries" not in results:
                return None

            entries = [e for e in results["entries"] if e]
            if not entries:
                return None

            best_entry = self._filter_entries(entries, query, duration)

            if best_entry:
                url = best_entry.get("webpage_url") or best_entry.get("url")
                sr = SearchResult(
                    url=url, title=best_entry.get("title", ""), duration=best_entry.get("duration", 0)
                )

                self.log.debug(f"Encontrado: {sr.title[:50]}")

                if self.app_cache and sr.url:
                    self.app_cache.set(cache_key, {"url": sr.url, "title": sr.title, "duration": sr.duration})

                # Register proxy success
                if self.proxy_manager and "proxy" in opts:
                    self.proxy_manager.mark_success(opts["proxy"])

                return sr

        except Exception as e:
            self.log.debug(f"Error búsqueda: {e}")
            # Register proxy failure if applicable
            if self.proxy_manager and "proxy" in opts:
                self.proxy_manager.mark_failure(opts["proxy"])
            
            # Raise wrapped error? Or just return None allows retry?
            # For now return None to treat as 'not found' in this attempt
            pass

        return None

    def _filter_entries(self, entries: list, query: str, duration: int) -> Optional[dict]:
        """Logic to filter best entry (Cpu bound but fast, can stay sync)"""
        best_entry = None
        best_diff = float("inf")

        for entry in entries:
            entry_duration = entry.get("duration", 0)
            entry_title = entry.get("title", "").lower()

            excludes = ["cover", "remix", "live", "karaoke", "instrumental"]
            if any(x in entry_title for x in excludes):
                if not any(x in query.lower() for x in excludes):
                    continue

            if duration and entry_duration:
                diff = abs(entry_duration - duration)
                if diff <= self.cfg.DURATION_TOLERANCE and diff < best_diff:
                    best_diff = diff
                    best_entry = entry
            elif not best_entry:
                best_entry = entry
        
        if not best_entry and entries:
            best_entry = entries[0]
            
        return best_entry
