"""
Polite HTTP client: shared session, per-host rate limiting, bounded retries for
transient failures, and an on-disk cache.

It never tries to bypass CAPTCHA, logins or anti-bot protection: a 401/403/429 or
a CAPTCHA page is logged and reported as "access restricted", not retried with
tricks.
"""
from __future__ import annotations

import hashlib
import json
import pickle
import time
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import requests

from config import CACHE_DIR, NETWORK
from utils.logger import get_logger

log = get_logger(__name__)

TRANSIENT_STATUS = {500, 502, 503, 504}
BLOCKED_STATUS = {401, 403, 429}


class AccessRestricted(Exception):
    """Raised when a site refuses access (auth, CAPTCHA, rate-limit). Not retried."""


class FetchError(Exception):
    """Raised when a request failed after retries."""


class DiskCache:
    def __init__(self, directory: Path = CACHE_DIR):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.dir / (hashlib.sha256(key.encode("utf-8")).hexdigest()[:32] + ".pkl")

    def get(self, key: str, ttl_hours: float) -> Any:
        p = self._path(key)
        if not p.exists():
            return None
        age_h = (time.time() - p.stat().st_mtime) / 3600.0
        if age_h > ttl_hours:
            return None
        try:
            with p.open("rb") as fh:
                return pickle.load(fh)
        except Exception as exc:  # noqa: BLE001 - corrupt cache entry
            log.debug("Cache read failed for %s: %s", key, exc)
            return None

    def set(self, key: str, value: Any) -> None:
        try:
            with self._path(key).open("wb") as fh:
                pickle.dump(value, fh)
        except Exception as exc:  # noqa: BLE001
            log.debug("Cache write failed for %s: %s", key, exc)

    def cached(self, key: str, ttl_hours: float, producer: Callable[[], Any]) -> Any:
        hit = self.get(key, ttl_hours)
        if hit is not None:
            log.debug("Cache hit: %s", key)
            return hit
        value = producer()
        if value is not None:
            self.set(key, value)
        return value


CACHE = DiskCache()

# Circuit breaker: hosts that failed to connect after all retries are skipped for
# the rest of the run (avoids minutes of repeated timeouts when a site is down).
_DOWN_HOSTS: set[str] = set()


def host_is_down(url: str) -> bool:
    return urlparse(url).netloc in _DOWN_HOSTS


class HttpClient:
    def __init__(self, extra_headers: Optional[dict] = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": NETWORK.user_agent,
            "Accept-Language": "en-IN,en;q=0.9",
        })
        if extra_headers:
            self.session.headers.update(extra_headers)
        self._last_call: dict[str, float] = {}

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        last = self._last_call.get(host)
        if last is not None:
            wait = NETWORK.min_delay_per_host - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_call[host] = time.time()

    def get(self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None,
            ttl_hours: Optional[float] = None, as_json: bool = False,
            use_cache: bool = True) -> Any:
        ttl = NETWORK.cache_ttl_fundamentals_hours if ttl_hours is None else ttl_hours
        key = "GET " + url + "?" + json.dumps(params or {}, sort_keys=True) + (" json" if as_json else "")
        if use_cache:
            hit = CACHE.get(key, ttl)
            if hit is not None:
                return hit

        host = urlparse(url).netloc
        if host in _DOWN_HOSTS:
            raise FetchError(f"{host} is unreachable in this run (skipped)")
        last_exc: Optional[Exception] = None
        connection_failures = 0
        for attempt in range(1, NETWORK.max_retries + 1):
            self._throttle(url)
            try:
                resp = self.session.get(url, params=params, headers=headers,
                                        timeout=NETWORK.timeout_seconds)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                connection_failures += 1
                log.info("Network error (%s/%s) for %s: %s", attempt, NETWORK.max_retries, url, exc)
                time.sleep(NETWORK.backoff_seconds * attempt)
                continue

            if resp.status_code in BLOCKED_STATUS:
                raise AccessRestricted(f"{url} returned HTTP {resp.status_code} (access restricted)")
            if resp.status_code in TRANSIENT_STATUS:
                last_exc = FetchError(f"HTTP {resp.status_code}")
                log.info("Transient HTTP %s (%s/%s) for %s", resp.status_code, attempt,
                            NETWORK.max_retries, url)
                time.sleep(NETWORK.backoff_seconds * attempt)
                continue
            if resp.status_code == 404:
                raise FetchError(f"{url} not found (404)")
            if resp.status_code >= 400:
                raise FetchError(f"{url} returned HTTP {resp.status_code}")

            text_low = resp.text[:3000].lower()
            if "captcha" in text_low or "are you a robot" in text_low:
                raise AccessRestricted(f"{url} presented a CAPTCHA / anti-bot check; not bypassing")

            if as_json:
                try:
                    data = resp.json()
                except ValueError as exc:
                    raise FetchError(f"{url} did not return JSON") from exc
            else:
                data = resp.text
            if use_cache:
                CACHE.set(key, data)
            return data
        if connection_failures == NETWORK.max_retries:
            _DOWN_HOSTS.add(host)
            log.warning("%s is unreachable (%s); skipping it for the rest of this run", host,
                        type(last_exc).__name__)
        raise FetchError(f"Failed to fetch {url} after {NETWORK.max_retries} attempts: {last_exc}")
