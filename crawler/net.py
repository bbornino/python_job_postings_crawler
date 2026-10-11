"""
crawler/net.py

Shared HTTP fetching for every scraper in the crawler.

fetch(url) is the one way scrapers should hit the network. It sends our
User-Agent, shows a live ticker while waiting, and backs off and retries
when a site answers 429 (Too Many Requests).

It does NOT pace requests. Each scraper sleeps between its own calls,
since the polite rate differs per site.
"""

import logging
import time
from urllib.parse import urlsplit
import requests
from crawler.utils import status_timer

logger = logging.getLogger(__name__)
HEADERS = {"User-Agent": "job-postings-crawler/0.1 (github.com/bbornino)"}
RETRY_WAITS = [30, 60, 120]     # seconds between attempts, used when the server doesn't say
# Longest Retry-After we'll honor. Below this the server means "slow down",
# so waiting works. Above it (an hour, a day) we're out of quota: fail now
# and let the next run pick it up.
MAX_WAIT = 300                  # seconds
REQUEST_TIMEOUT = (10, 60)      # seconds: (to connect, between chunks of the response)

def fetch(url: str) -> requests.Response:
    """GET `url`, waiting out 429 (Too Many Requests) throttling.

    Site-agnostic: callers pick the format with fetch(url).json() or
    fetch(url).text. Tries once plus one retry per RETRY_WAITS entry
    (about 3.5 minutes worst case on our schedule, up to 15 if the server
    keeps asking for MAX_WAIT). Raises requests.HTTPError if still refused
    after the last attempt, or if the server asks for more than MAX_WAIT.

    Only 429 is retried. Timeouts, connection errors and 5xx raise right away.
    """
    host = urlsplit(url).netloc
    for wait in [*RETRY_WAITS, None]:   # None marks the final attempt: no wait left
        # Ticker on every request: a slow server can take a minute or more,
        # and without it the app looks frozen.
        started = time.monotonic()
        with status_timer(f"Fetching from {host}"):
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        # Seconds for this request, so a slowing server shows up in the log
        # and not only in the on-screen ticker.
        elapsed = time.monotonic() - started
        logger.info("%s %s (%.1fs)", response.status_code, url, elapsed)
        if response.status_code != 429 or wait is None:
            response.raise_for_status()
            return response

        # Prefer the server's own back-off time. Retry-After can also be an
        # HTTP date; in that case fall back to our schedule rather than parse it.
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            wait = int(retry_after)
            if wait > MAX_WAIT:       # e.g. a daily quota: retrying today is pointless
                logger.error("429 from %s, Retry-After %ss exceeds MAX_WAIT", host, wait)
                response.raise_for_status()
        logger.warning("429 from %s (Retry-After: %r), waiting %ss", host, retry_after, wait)
        with status_timer(f"Waiting out {host} throttle"):
            time.sleep(wait)
