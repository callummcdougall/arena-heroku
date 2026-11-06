"""
ETag-based in-memory cache for GitHub raw content fetches.

Uses conditional requests (If-None-Match) so content is always fresh
but most requests are served instantly from cache. A 60-second grace
period skips validation entirely for recently-validated entries.
"""

import logging
import threading
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

GRACE_PERIOD_SECONDS = 60


@dataclass
class CacheEntry:
    content: str
    etag: str
    last_validated: float


_cache: dict[str, CacheEntry] = {}
_lock = threading.Lock()


def fetch_github_text(url: str, extra_headers: dict[str, str] | None = None) -> str:
    """
    Fetch text from a GitHub raw URL with ETag-based caching.

    Flow:
      1. Cached & validated <60s ago -> return instantly
      2. Cached & stale -> send If-None-Match -> 304 keeps cache, 200 updates it
      3. Not cached -> normal GET, store content + ETag
      4. Network error + cache exists -> serve stale (graceful degradation)

    Raises requests.HTTPError for non-OK responses (caller handles 404 etc.).
    """
    headers = dict(extra_headers) if extra_headers else {}
    now = time.time()

    with _lock:
        entry = _cache.get(url)

    # 1. Fresh cache hit
    if entry and (now - entry.last_validated) < GRACE_PERIOD_SECONDS:
        logger.debug("Cache HIT (fresh) for %s", url)
        return entry.content

    # 2/3. Stale or missing — make a (conditional) request
    if entry and entry.etag:
        headers["If-None-Match"] = entry.etag

    try:
        resp = requests.get(url, headers=headers, timeout=10)

        if resp.status_code == 304 and entry:
            logger.debug("Cache REVALIDATED (304) for %s", url)
            with _lock:
                current = _cache.get(url, entry)
                current.last_validated = now
            return current.content

        resp.raise_for_status()

        new_etag = resp.headers.get("ETag", "")
        new_entry = CacheEntry(content=resp.text, etag=new_etag, last_validated=now)
        with _lock:
            _cache[url] = new_entry

        if entry:
            logger.debug("Cache UPDATED (200) for %s", url)
        else:
            logger.debug("Cache MISS for %s", url)

        return resp.text

    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (404, 410):
            # The file is gone (e.g. a closed PR's preview was removed): drop it
            # rather than serving the old copy until the process restarts.
            with _lock:
                _cache.pop(url, None)
            raise
        return _serve_stale(url, entry, now)
    except requests.RequestException:
        return _serve_stale(url, entry, now)


def _serve_stale(url: str, entry: CacheEntry | None, now: float) -> str:
    """
    4. Network error, rate limit or 5xx: serve stale if available (re-raising the
    current exception otherwise). The entry counts as validated now, so while
    GitHub is down each URL is retried once per grace period instead of every
    request waiting for the timeout.
    """
    if entry is None:
        raise  # noqa: PLE0704 - called only from an except block
    logger.warning("Error fetching %s — serving stale cache", url)
    with _lock:
        entry.last_validated = now
    return entry.content


def invalidate_cache(url: str | None = None) -> None:
    """Clear one or all cache entries."""
    with _lock:
        if url is None:
            _cache.clear()
        else:
            _cache.pop(url, None)
