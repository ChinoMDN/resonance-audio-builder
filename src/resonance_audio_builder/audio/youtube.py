import asyncio
import random
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

import yt_dlp

from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.core.config import Config
from resonance_audio_builder.core.exceptions import NotFoundError
from resonance_audio_builder.core.logger import Logger
from resonance_audio_builder.network.cache import CacheManager
from resonance_audio_builder.network.proxies import SmartProxyManager
from resonance_audio_builder.network.utils import USER_AGENTS, validate_cookies_file


@dataclass
class SearchResult:
    """Result from a YouTube search query."""

    url: str
    title: str
    duration: int
    cached: bool = False


class YouTubeSearcher:
    """Async YouTube search engine using yt-dlp with caching and proxy support."""

    QUERY_TEMPLATES = [
        "{artist} - {title} Audio",
        "{artist} {title} - Topic",
        "{artist} {title} Official Audio",
    ]

    HARD_EXCLUDES = ("cover", "remix", "live", "karaoke", "instrumental")
    VERSION_PENALTY_TOKENS = frozenset(
        (
            "lyrics",
            "lyric",
            "house",
            "slowed",
            "nightcore",
            "8d",
        )
    )
    VERSION_PENALTY_PHRASES = (
        "vocals only",
        "korean ver",
        "english ver",
        "from the first take",
        "sped up",
    )
    DURATION_SOFT_CAP_SECONDS = 30
    DURATION_HARD_PENALTY = 15.0

    def __init__(
        self,
        config: Config,
        logger: Logger,
        cache_manager: CacheManager,
        proxy_manager: Optional[SmartProxyManager] = None,
    ):
        self.cfg = config
        self.log = logger
        self.app_cache = cache_manager
        self.proxy_manager = proxy_manager
        self._cookies_valid = validate_cookies_file(config.COOKIES_FILE)
        max_workers = max(1, int(getattr(self.cfg, "MAX_CONCURRENT_SEARCHES", 4)))
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="yt_search")

    def close(self):
        """Release search executor resources."""
        self._executor.shutdown(wait=False)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _get_from_cache(self, cache_key: str, ttl_hours: int) -> Optional[SearchResult]:
        """Try to get result from cache."""
        if not self.app_cache:
            return None
        cached = self.app_cache.get(cache_key, ttl_hours=ttl_hours)
        if cached:
            self.log.debug(f"Cache hit: {cached.get('title', '')[:50]}")
            return SearchResult(cached["url"], cached["title"], cached["duration"], cached=True)
        return None

    def _store_in_cache(self, track_key: str, result: SearchResult, isrc: Optional[str] = None):
        """Store result in cache with optional ISRC key."""
        if not self.app_cache:
            return
        cache_data = {"url": result.url, "title": result.title, "duration": result.duration}
        self.app_cache.set(track_key, cache_data)
        if isrc:
            self.app_cache.set(f"isrc_{isrc}", cache_data)

    async def search(self, track: TrackMetadata) -> SearchResult:
        """Async search implementation with global scoring across templates."""
        # 1. Check ISRC Cache
        if track.isrc and self.app_cache:
            cached = self._get_from_cache(f"isrc_{track.isrc}", ttl_hours=24 * 30)
            if cached:
                return cached
            self.log.debug("ISRC sin cache: se omite lookup directo en YouTube para evitar falsos positivos")

        candidates: list[tuple[float, SearchResult]] = []

        # 2. Try configurable text queries
        for template in self.QUERY_TEMPLATES:
            query = template.format(artist=track.artist, title=track.title)
            cache_key = query.lower().strip()[:100]

            cached = self._get_from_cache(cache_key, ttl_hours=24 * 7)
            if cached:
                return cached

            result = await self._lookup(cache_key, query, track.duration_seconds)
            if result:
                candidates.append(result)

        if not candidates:
            raise NotFoundError(f"No encontrado: {track.artist} - {track.title}")

        best_score, best_result = max(candidates, key=lambda x: x[0])
        self.log.debug(f"Seleccionado global: {best_result.title[:50]} (score={best_score:+.2f})")

        track_key = f"{track.artist} - {track.title}".lower().strip()[:100]
        self._store_in_cache(track_key, best_result, track.isrc)

        return best_result

    async def _extract_from_yt(self, query: str) -> Optional[list]:
        """Extract YouTube search entries only (no cache decisions)."""
        opts = await self._get_search_options()
        loop = asyncio.get_running_loop()

        try:

            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(f"ytsearch5:{query}", download=False)

            results = await loop.run_in_executor(self._executor, _extract)

            if self.proxy_manager and "proxy" in opts:
                self.proxy_manager.mark_success(opts["proxy"])

            return (results or {}).get("entries") or []
        except Exception as e:
            self.log.debug(f"Error extracción yt-dlp: {e}")
            if self.proxy_manager and "proxy" in opts:
                self.proxy_manager.mark_failure(opts["proxy"])
            return None

    async def _get_search_options(self) -> dict:
        """Configura las opciones de búsqueda de yt-dlp"""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "noplaylist": True,
            "socket_timeout": self.cfg.SEARCH_TIMEOUT,
            # nosec B311
            "http_headers": {"User-Agent": random.choice(USER_AGENTS)},
        }

        if self.proxy_manager:
            proxy = await self.proxy_manager.get_proxy_async()
            if proxy:
                opts["proxy"] = proxy

        if self._cookies_valid:
            opts["cookiefile"] = self.cfg.COOKIES_FILE

        return opts

    async def _lookup(self, cache_key: str, query: str, duration: int) -> Optional[tuple[float, SearchResult]]:
        entries = await self._extract_from_yt(query)
        if not entries:
            return None

        entries = [e for e in entries if e]
        if not entries:
            return None

        scored = [(self._score_entry(e, query, duration), e) for e in entries if e]

        self.log.debug(f"Query: {query!r} | Candidatos:")
        for score, entry in sorted(scored, key=lambda x: x[0], reverse=True):
            self.log.debug(f"  [{score:+.1f}] {entry.get('title', '')[:60]} ({entry.get('duration', 0)}s)")

        valid = [(s, e) for s, e in scored if s > float("-inf")]
        if not valid:
            return None

        best_score, best_entry = max(valid, key=lambda x: x[0])

        url = best_entry.get("webpage_url") or best_entry.get("url")
        if not url:
            self.log.debug("Entry sin URL válida, descartando")
            return None

        sr = SearchResult(url=url, title=best_entry.get("title", ""), duration=best_entry.get("duration", 0))
        self.log.debug(f"Encontrado: {sr.title[:50]}")

        if self.app_cache:
            self.app_cache.set(cache_key, {"url": sr.url, "title": sr.title, "duration": sr.duration})

        return best_score, sr

    def _score_entry(self, entry: dict, query: str, duration: int) -> float:
        """Compute relevance score for a candidate entry."""
        entry_title = entry.get("title", "")
        title_norm = self._normalize_for_phrase_match(entry_title)
        title_tokens = set(re.findall(r"[a-z0-9]+", title_norm))
        query_tokens = self._tokenize(query)
        hard_excludes = set(self.HARD_EXCLUDES)

        if title_tokens & hard_excludes and not query_tokens & hard_excludes:
            self.log.debug(f"Score descartado por exclude: {entry_title[:60]} | query={query!r}")
            return float("-inf")

        score = 0.0
        duration_penalty = 0.0
        version_penalty = 0.0

        entry_duration = entry.get("duration", 0)
        if duration and entry_duration:
            diff = abs(entry_duration - duration)
            if diff > self.DURATION_SOFT_CAP_SECONDS:
                duration_penalty = self.DURATION_HARD_PENALTY
            else:
                duration_penalty = diff * 0.1
            score -= duration_penalty
        else:
            diff = None

        overlap = len(query_tokens & title_tokens)
        overlap_bonus = overlap * 2.0
        score += overlap_bonus

        token_hits = len(title_tokens & self.VERSION_PENALTY_TOKENS)
        phrase_hits = sum(1 for phrase in self.VERSION_PENALTY_PHRASES if phrase in title_norm)
        version_hits_count = token_hits + phrase_hits
        if version_hits_count:
            version_penalty = version_hits_count * 2.0
            score -= version_penalty

        uploader = entry.get("uploader", "").lower()
        topic_bonus = 0.0
        if "- topic" in uploader:
            topic_bonus = 1.5
            score += topic_bonus

        diff_text = "n/a" if diff is None else str(diff)
        self.log.debug(
            "Score detalle | "
            f"title={entry_title[:60]!r} | "
            f"query={query!r} | "
            f"diff={diff_text} | "
            f"dur_penalty={duration_penalty:.2f} | "
            f"overlap={overlap} (+{overlap_bonus:.2f}) | "
            f"version_penalty={version_penalty:.2f} | "
            f"topic_bonus=+{topic_bonus:.2f} | "
            f"total={score:+.2f}"
        )

        return score

    def _tokenize(self, text: str) -> set[str]:
        """Normalize accents/symbols and return alphanumeric tokens."""
        ascii_text = self._normalize_for_phrase_match(text)
        return set(re.findall(r"[a-z0-9]+", ascii_text))

    def _normalize_for_phrase_match(self, text: str) -> str:
        """Normalize unicode text to lowercase ASCII for stable comparisons."""
        normalized = unicodedata.normalize("NFD", text)
        return normalized.encode("ascii", "ignore").decode("ascii").lower()
