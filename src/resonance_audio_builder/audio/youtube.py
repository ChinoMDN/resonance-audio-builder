import asyncio
import math
import random
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

import aiohttp
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

    ALBUM_QUERY_TEMPLATES = [
        "{artist} {title} {album} Audio",
    ]

    HARD_EXCLUDES = (
        "cover",
        "remix",
        "live",
        "karaoke",
        "instrumental",
        "mashup",
        "tutorial",
        "reaction",
        "parodia",
        "parody",
    )
    VERSION_PENALTY_TOKENS = frozenset(
        (
            "lyrics",
            "lyric",
            "house",
            "slowed",
            "nightcore",
            "8d",
            "reverb",
            "bass",
            "boosted",
            "extended",
            "acoustic",
            "unplugged",
            "stripped",
            "demo",
            "rehearsal",
        )
    )
    VERSION_PENALTY_PHRASES = (
        "vocals only",
        "korean ver",
        "english ver",
        "from the first take",
        "sped up",
        "music video",
        "official video",
        "behind the scenes",
        "making of",
        "piano version",
        "guitar version",
    )
    DURATION_SOFT_CAP_SECONDS = 30
    DURATION_HARD_PENALTY = 15.0
    MIN_SCORE_THRESHOLD = -5.0
    SHORT_ARTIST_TOKEN_LIMIT = 2
    MATCH_STOPWORDS = frozenset(("the", "a", "an", "and", "feat", "featuring", "ft", "x"))

    _TITLE_CLEAN_RE = re.compile(
        r"\s*[\(\[](feat\.?|ft\.?|featuring|with|remaster|bonus|deluxe|"
        r"from\s+[\"']|version|edit|radio)[^\)\]]*[\)\]]",
        re.IGNORECASE,
    )
    _TITLE_SUFFIX_RE = re.compile(
        r"\s*-\s*(remaster|bonus\s+track|deluxe|anniversary|edition).*$",
        re.IGNORECASE,
    )
    _PAREN_CONTENT_RE = re.compile(r"[\(\[][^\)\]]*[\)\]]")

    INVIDIOUS_SEARCH_INSTANCES = (
        "https://invidious.privacyredirect.com",
        "https://yewtu.be",
        "https://invidious.fdn.fr",
    )

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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ── Cache helpers ───────────────────────────────────────────────────

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

    # ── Main search entry point ─────────────────────────────────────────

    async def search(self, track: TrackMetadata) -> SearchResult:
        """Async search: ISRC first, then text queries with global scoring."""
        # 1. Check ISRC Cache
        if track.isrc and self.app_cache:
            cached = self._get_from_cache(f"isrc_{track.isrc}", ttl_hours=24 * 30)
            if cached:
                return cached

        # 2. Try ISRC lookup on YouTube (most reliable identifier)
        if track.isrc:
            result = await self._isrc_lookup(track)
            if result:
                track_key = f"{track.artist} - {track.title}".lower().strip()[:100]
                self._store_in_cache(track_key, result, track.isrc)
                return result

        # 3. Text-based search with scoring
        candidates = await self._search_text_candidates(track)

        if not candidates:
            raise NotFoundError(f"No encontrado: {track.artist} - {track.title}")

        return self._select_best_candidate(candidates, track)

    async def _search_text_candidates(self, track: TrackMetadata) -> list[tuple[float, SearchResult]]:
        """Run text-based queries and collect scored candidates."""
        candidates: list[tuple[float, SearchResult]] = []
        clean_title = self._clean_query_title(track.title)

        for template in self.QUERY_TEMPLATES:
            query = template.format(artist=track.artist, title=clean_title)
            cache_key = query.lower().strip()[:100]

            cached = self._get_from_cache(cache_key, ttl_hours=24 * 7)
            if cached:
                return [(0.0, cached)]  # Cache hit, return immediately

            result = await self._lookup(cache_key, query, track)
            if result:
                candidates.append(result)

        # For short/generic artist names, try album-disambiguated queries
        if self._is_short_artist(track) and track.album:
            candidates.extend(await self._search_album_candidates(track, clean_title))

        return candidates

    async def _search_album_candidates(self, track: TrackMetadata, clean_title: str) -> list:
        """Album-disambiguated queries for short/generic artist names."""
        results = []
        clean_album = self._clean_query_title(track.album)
        for template in self.ALBUM_QUERY_TEMPLATES:
            query = template.format(artist=track.artist, title=clean_title, album=clean_album)
            cache_key = query.lower().strip()[:100]
            result = await self._lookup(cache_key, query, track)
            if result:
                results.append(result)
        return results

    def _select_best_candidate(self, candidates: list, track: TrackMetadata) -> SearchResult:
        """Pick the highest-scoring candidate and reject if below threshold."""
        best_score, best_result = max(candidates, key=lambda x: x[0])

        if best_score < self.MIN_SCORE_THRESHOLD:
            self.log.warning(
                f"Mejor candidato descartado por score bajo ({best_score:.1f}): "
                f"{best_result.title[:50]} | buscando: {track.artist} - {track.title}"
            )
            raise NotFoundError(f"No encontrado (score bajo): {track.artist} - {track.title}")

        self.log.debug(f"Seleccionado global: {best_result.title[:50]} (score={best_score:+.2f})")

        track_key = f"{track.artist} - {track.title}".lower().strip()[:100]
        self._store_in_cache(track_key, best_result, track.isrc)
        return best_result

    # ── ISRC-based lookup ───────────────────────────────────────────────

    async def _isrc_lookup(self, track: TrackMetadata) -> Optional[SearchResult]:
        """Search YouTube using ISRC code for exact match."""
        query = f'"{track.isrc}"'
        entries = await self._extract_from_yt(query)

        if not entries:
            self.log.debug(f"ISRC lookup sin resultados: {track.isrc}")
            return None

        entries = [e for e in entries if e]
        if not entries:
            return None

        # For ISRC results, apply strict duration validation
        for entry in entries:
            entry_duration = entry.get("duration", 0)
            url = entry.get("webpage_url") or entry.get("url")
            if not url:
                continue

            if track.duration_seconds and entry_duration:
                diff = abs(entry_duration - track.duration_seconds)
                if diff > self.DURATION_SOFT_CAP_SECONDS:
                    self.log.debug(
                        f"ISRC candidato descartado por duración: " f"{entry.get('title', '')[:50]} (diff={diff}s)"
                    )
                    continue
                diff_text = str(diff)
            else:
                diff_text = "n/a"

            sr = SearchResult(url=url, title=entry.get("title", ""), duration=entry_duration)
            self.log.debug(f"ISRC match: {sr.title[:50]} (diff={diff_text}s)")
            return sr

        self.log.debug(f"ISRC lookup: todos los candidatos descartados: {track.isrc}")
        return None

    # ── yt-dlp extraction ───────────────────────────────────────────────

    async def _extract_from_yt(self, query: str) -> Optional[list]:
        """Extract YouTube search entries only (no cache decisions)."""
        loop = asyncio.get_running_loop()
        all_opts = await self._get_search_options_variants()

        last_error: Optional[Exception] = None
        for opts in all_opts:
            try:

                def _extract():
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(f"ytsearch5:{query}", download=False)

                results = await loop.run_in_executor(self._executor, _extract)

                if self.proxy_manager and "proxy" in opts:
                    self.proxy_manager.mark_success(opts["proxy"])

                return (results or {}).get("entries") or []
            except Exception as e:
                last_error = e
                self.log.debug(f"Error extracción yt-dlp: {e}")
                if self.proxy_manager and "proxy" in opts:
                    self.proxy_manager.mark_failure(opts["proxy"])

        if last_error:
            self.log.debug(f"Búsqueda agotada tras fallbacks: {last_error}")

        fallback_entries = await self._extract_from_invidious(query)
        if fallback_entries:
            self.log.debug(f"Fallback Invidious OK: {len(fallback_entries)} candidatos")
            return fallback_entries

        return None

    async def _extract_from_invidious(self, query: str) -> Optional[list]:
        """Fallback search path using public Invidious instances."""
        timeout_seconds = max(8, int(getattr(self.cfg, "SEARCH_TIMEOUT", 30)))
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        headers = {"User-Agent": random.choice(USER_AGENTS)}  # nosec B311

        for base_url in self.INVIDIOUS_SEARCH_INSTANCES:
            try:
                entries = await self._fetch_invidious_instance(base_url, query, timeout, headers)
                if entries:
                    return entries
            except Exception as e:
                self.log.debug(f"Fallback Invidious error ({base_url}): {e}")

        return None

    async def _fetch_invidious_instance(self, base_url: str, query: str, timeout, headers) -> Optional[list]:
        """Fetch search results from a single Invidious instance."""
        search_url = f"{base_url}/api/v1/search"
        params = {"q": query, "type": "video", "sort_by": "relevance"}

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(search_url, params=params) as resp:
                if resp.status != 200:
                    self.log.debug(f"Invidious HTTP {resp.status}: {base_url}")
                    return None

                data = await resp.json(content_type=None)
                if not isinstance(data, list):
                    return None

                return self._parse_invidious_entries(data) or None

    def _parse_invidious_entries(self, data: list) -> list:
        """Parse Invidious API response into normalized entry dicts."""
        entries = []
        for item in data:
            if item.get("type") != "video":
                continue

            video_id = item.get("videoId")
            if not video_id:
                continue

            duration = self._parse_duration(item.get("lengthSeconds") or item.get("length"))
            author = item.get("author", "")
            entries.append(
                {
                    "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "title": item.get("title", ""),
                    "duration": duration,
                    "uploader": author,
                    "channel": author,
                }
            )

            if len(entries) >= 5:
                break

        return entries

    async def _get_search_options_variants(self) -> list[dict]:
        """Configura las opciones de búsqueda de yt-dlp"""
        base_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "noplaylist": True,
            "socket_timeout": self.cfg.SEARCH_TIMEOUT,
            "retries": 2,
            # nosec B311
            "http_headers": {"User-Agent": random.choice(USER_AGENTS)},
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"],
                }
            },
        }

        if self.proxy_manager:
            proxy = await self.proxy_manager.get_proxy_async()
            if proxy:
                base_opts["proxy"] = proxy

        if self._cookies_valid:
            base_opts["cookiefile"] = self.cfg.COOKIES_FILE

        # Fallback with less restrictive extractor args
        fallback_opts = dict(base_opts)
        fallback_opts["extractor_args"] = {"youtube": {"player_client": ["web"]}}

        return [base_opts, fallback_opts]

    # ── Text-based scoring lookup ───────────────────────────────────────

    async def _lookup(self, cache_key: str, query: str, track: TrackMetadata) -> Optional[tuple[float, SearchResult]]:
        entries = await self._extract_from_yt(query)
        if not entries:
            return None

        entries = [e for e in entries if e]
        if not entries:
            return None

        scored = [(self._score_entry(e, query, track), e) for e in entries if e]

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

    # ── Scoring engine ──────────────────────────────────────────────────

    def _score_entry(self, entry: dict, query: str, track: TrackMetadata) -> float:
        """Compute relevance score for a candidate entry."""
        entry_title = entry.get("title", "")
        uploader = entry.get("uploader", "")
        channel = entry.get("channel", "")

        title_norm = self._normalize_for_phrase_match(entry_title)
        title_tokens = set(re.findall(r"[a-z0-9]+", title_norm))
        query_tokens = self._tokenize(query)
        combined_text = f"{entry_title} {uploader} {channel}"
        combined_tokens = self._tokenize(combined_text)

        # ── Validate entry (returns -inf if invalid) ────────────────
        all_artists = track.artists if hasattr(track, "artists") else [track.artist]
        artist_token_sets = [self._essential_tokens(a) for a in all_artists]
        all_artist_tokens = set().union(*artist_token_sets) if artist_token_sets else set()
        artist_overlap_count = len(all_artist_tokens & combined_tokens)

        combined_norm = self._normalize_for_phrase_match(combined_text)
        artist_phrase_match = any(self._normalize_for_phrase_match(a) in combined_norm for a in all_artists)

        rejection = self._validate_entry_candidates(
            entry_title,
            uploader,
            channel,
            query,
            track,
            title_tokens,
            query_tokens,
            all_artist_tokens,
            artist_overlap_count,
            artist_phrase_match,
        )
        if rejection is not None:
            return rejection

        # ── Compute score bonuses ───────────────────────────────────
        title_required_tokens = self._essential_tokens(track.title)
        title_overlap_count = len(title_required_tokens & title_tokens)
        required_title_hits = self._required_title_overlap(len(title_required_tokens))

        (
            score,
            diff,
            duration_penalty,
            overlap,
            overlap_bonus,
            version_penalty,
            topic_bonus,
            artist_bonus,
            album_bonus,
        ) = self._compute_score_components(
            entry,
            query,
            track,
            title_norm,
            title_tokens,
            query_tokens,
            entry_title,
            uploader,
            all_artist_tokens,
            artist_overlap_count,
            artist_phrase_match,
        )

        diff_text = "n/a" if diff is None else str(diff)
        self.log.debug(
            "Score detalle | "
            f"title={entry_title[:60]!r} | "
            f"query={query!r} | "
            f"diff={diff_text} | "
            f"dur_penalty={duration_penalty:.2f} | "
            f"overlap={overlap} (+{overlap_bonus:.2f}) | "
            f"artist_hits={artist_overlap_count} (+{artist_bonus:.2f}) | "
            f"title_hits={title_overlap_count}/{required_title_hits} | "
            f"version_penalty={version_penalty:.2f} | "
            f"topic_bonus=+{topic_bonus:.2f} | "
            f"album_bonus=+{album_bonus:.2f} | "
            f"total={score:+.2f}"
        )

        return score

    def _validate_entry_candidates(
        self,
        entry_title,
        uploader,
        channel,
        query,
        track,
        title_tokens,
        query_tokens,
        all_artist_tokens,
        artist_overlap_count,
        artist_phrase_match,
    ) -> Optional[float]:
        """Check hard disqualifications. Returns -inf if invalid, None if OK."""
        # Title validation
        title_required_tokens = self._essential_tokens(track.title)
        title_overlap_count = len(title_required_tokens & title_tokens)
        required_title_hits = self._required_title_overlap(len(title_required_tokens))

        if title_required_tokens and title_overlap_count < required_title_hits:
            self.log.debug(
                f"Score descartado por titulo insuficiente: {entry_title[:60]} | "
                f"hits={title_overlap_count}/{required_title_hits}"
            )
            return float("-inf")

        # Artist incompatibility
        creator_tokens = self._tokenize(f"{uploader} {channel}")
        if all_artist_tokens and creator_tokens and not artist_phrase_match:
            if artist_overlap_count == 0:
                self.log.debug(f"Score descartado por artista incompatible: {entry_title[:60]} | query={query!r}")
                return float("-inf")

        # Hard excludes
        hard_excludes = set(self.HARD_EXCLUDES)
        if title_tokens & hard_excludes and not query_tokens & hard_excludes:
            self.log.debug(f"Score descartado por exclude: {entry_title[:60]} | query={query!r}")
            return float("-inf")

        return None

    def _compute_score_components(  # noqa: C901
        self,
        entry,
        query,
        track,
        title_norm,
        title_tokens,
        query_tokens,
        entry_title,
        uploader,
        all_artist_tokens,
        artist_overlap_count,
        artist_phrase_match,
    ) -> tuple:
        """Compute all score bonuses/penalties and return components."""
        score = 0.0
        duration = track.duration_seconds

        # Duration penalty
        entry_duration = entry.get("duration", 0)
        if duration and entry_duration:
            diff = abs(entry_duration - duration)
            duration_penalty = self.DURATION_HARD_PENALTY if diff > self.DURATION_SOFT_CAP_SECONDS else diff * 0.15
            score -= duration_penalty
        else:
            diff = None
            duration_penalty = 0.0

        # Query-token overlap bonus
        clean_title_tokens = self._strip_parenthetical_tokens(entry_title, query)
        overlap = len(query_tokens & clean_title_tokens)
        overlap_bonus = overlap * 2.0
        score += overlap_bonus

        # Version penalty
        token_hits = len(title_tokens & self.VERSION_PENALTY_TOKENS)
        phrase_hits = sum(1 for phrase in self.VERSION_PENALTY_PHRASES if phrase in title_norm)
        version_hits_count = token_hits + phrase_hits
        version_penalty = version_hits_count * 2.5 if version_hits_count else 0.0
        score -= version_penalty

        # Topic channel bonus
        topic_bonus = self._compute_topic_bonus(uploader, all_artist_tokens)
        score += topic_bonus

        # Artist match bonus
        artist_bonus = self._compute_artist_bonus(artist_overlap_count, artist_phrase_match, all_artist_tokens)
        score += artist_bonus

        # Album match bonus
        album_bonus = self._compute_album_bonus(track, title_tokens)
        score += album_bonus

        return (
            score,
            diff,
            duration_penalty,
            overlap,
            overlap_bonus,
            version_penalty,
            topic_bonus,
            artist_bonus,
            album_bonus,
        )

    def _compute_topic_bonus(self, uploader: str, all_artist_tokens: set) -> float:
        """Score bonus for Topic channels matching the artist."""
        uploader_lower = uploader.lower()
        if "- topic" not in uploader_lower:
            return 0.0
        topic_name = uploader_lower.replace("- topic", "").strip()
        topic_tokens = self._essential_tokens(topic_name)
        if all_artist_tokens and topic_tokens & all_artist_tokens:
            return 3.0
        return 0.5

    def _compute_artist_bonus(self, overlap_count: int, phrase_match: bool, all_tokens: set) -> float:
        """Score bonus/penalty for artist matching."""
        if overlap_count:
            bonus = overlap_count * 1.5
            if phrase_match:
                bonus += 2.0
            return bonus
        return -3.0 if all_tokens else 0.0

    def _compute_album_bonus(self, track: TrackMetadata, title_tokens: set) -> float:
        """Score bonus for album name appearing in video title."""
        if not track.album:
            return 0.0
        album_tokens = self._essential_tokens(track.album)
        album_hits = len(album_tokens & title_tokens)
        return album_hits * 1.0 if album_hits else 0.0

    # ── Utility methods ─────────────────────────────────────────────────

    def _tokenize(self, text: str) -> set[str]:
        """Normalize accents/symbols and return alphanumeric tokens."""
        ascii_text = self._normalize_for_phrase_match(text)
        return set(re.findall(r"[a-z0-9]+", ascii_text))

    def _essential_tokens(self, text: str) -> set[str]:
        """Tokenize text and remove low-signal words that hurt matching precision."""
        return {tok for tok in self._tokenize(text) if tok not in self.MATCH_STOPWORDS and len(tok) > 1}

    def _required_title_overlap(self, title_token_count: int) -> int:
        """Compute minimum title token hits required to accept a candidate."""
        if title_token_count <= 1:
            return title_token_count
        return max(1, int(math.ceil(title_token_count * 0.5)))

    def _clean_query_title(self, title: str) -> str:
        """Remove Spotify suffixes like (feat. ...), (Remastered ...), etc."""
        cleaned = self._TITLE_CLEAN_RE.sub("", title)
        cleaned = self._TITLE_SUFFIX_RE.sub("", cleaned)
        return cleaned.strip() or title

    def _is_short_artist(self, track: TrackMetadata) -> bool:
        """Check if artist name is short/generic and prone to ambiguity."""
        tokens = self._essential_tokens(track.artist)
        return len(tokens) <= self.SHORT_ARTIST_TOKEN_LIMIT

    def _strip_parenthetical_tokens(self, entry_title: str, query: str) -> set[str]:
        """Return title tokens excluding parenthetical content not in query.

        Prevents tokens from (Official Video), (feat. X), etc. inflating the
        query-overlap bonus when those tokens don't appear in the search query.
        """
        paren_spans = list(self._PAREN_CONTENT_RE.finditer(entry_title))
        if not paren_spans:
            return self._tokenize(entry_title)

        q_tokens = self._tokenize(query)
        noise_tokens: set[str] = set()
        for m in paren_spans:
            paren_toks = self._tokenize(m.group())
            noise_tokens |= paren_toks - q_tokens

        return self._tokenize(entry_title) - noise_tokens

    def _parse_duration(self, raw_value) -> int:
        """Parse duration from int or mm:ss-like strings into seconds."""
        if raw_value is None:
            return 0

        if isinstance(raw_value, int):
            return max(raw_value, 0)

        if isinstance(raw_value, str):
            value = raw_value.strip()
            if not value:
                return 0

            if value.isdigit():
                return int(value)

            if ":" in value:
                parts = value.split(":")
                if all(p.isdigit() for p in parts):
                    seconds = 0
                    for part in parts:
                        seconds = seconds * 60 + int(part)
                    return seconds

        return 0

    def _normalize_for_phrase_match(self, text: str) -> str:
        """Normalize unicode text to lowercase ASCII for stable comparisons."""
        normalized = unicodedata.normalize("NFD", text)
        return normalized.encode("ascii", "ignore").decode("ascii").lower()
