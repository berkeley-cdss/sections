"""Student photos from the Cal 1 Card office's API (C1C), for roster photos (#4).

Works like seating's server/services/c1c/__init__.py, which has used this API
since 2024, and takes the same settings. C1C only answers requests from
allowlisted addresses, so requests go through C1C_PROXY_URL when it's set.
"""

import logging
import re
import sys
import time

import requests
from flask import current_app

from server.cache import cache_key_photo, cache_store

# Seconds to wait for C1C: up to 3 to connect, then up to 5 for each wait for
# data (seating waits 10 for each). A page asks for every photo at once, so a
# slow C1C mustn't hold the server's threads for long; the roster shows the
# placeholder instead.
TIMEOUT = (3, 5)

# One line per call to C1C: its status (or error) and how long it took. Its own
# handler at INFO, like audit_log in api_keys.py, because the app's logger drops
# INFO lines outside debug mode. Never logs the SID.
c1c_log = logging.getLogger("sections.c1c")
if not c1c_log.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    c1c_log.addHandler(_handler)
    c1c_log.setLevel(logging.INFO)
    c1c_log.propagate = False


# Input: sid, a student's ID number.
# Output: (image bytes, content type), or None if there's no photo.
# Description: Development uses a made-up picture (fake_photo) unless
# MOCK_C1C=false. Real photos are kept in cache_store, so reloads skip C1C. With
# no C1C settings, or if C1C fails, there's no photo and nothing is cached.
def get_photo(sid: str) -> tuple[bytes, str] | None:
    # As in seating: the SID goes into C1C's URL, so anything but digits (like
    # "../") could send the request to a different C1C address.
    if not re.fullmatch(r"[0-9]+", sid):
        return None
    config = current_app.config
    if config.get("MOCK_C1C"):
        return fake_photo(sid)
    if not config.get("C1C_API_DOMAIN"):
        return None
    cached_photo = cache_store.get(cache_key_photo(sid))
    if cached_photo is not None:
        return cached_photo, "image/jpeg"
    proxy_url = config.get("C1C_PROXY_URL")
    started_at = time.perf_counter()
    try:
        response = requests.get(
            config["C1C_API_DOMAIN"].rstrip("/") + f"/c1c-api/v1/photo/{sid}",
            auth=(config["C1C_API_USERNAME"], config["C1C_API_PASSWORD"]),
            proxies={"http": proxy_url, "https": proxy_url} if proxy_url else None,
            timeout=TIMEOUT,
        )
    except requests.RequestException as error:
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        # Only the error's type (like ReadTimeout): its message has the URL, which has the SID.
        c1c_log.warning("c1c_photo error=%s ms=%.1f", type(error).__name__, elapsed_ms)
        return None
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    # 200 is a photo and 404 (we expect) a student without one; others need a look.
    level = logging.INFO if response.status_code in (200, 404) else logging.WARNING
    c1c_log.log(level, "c1c_photo status=%d ms=%.1f", response.status_code, elapsed_ms)
    if response.status_code != 200:
        return None
    cache_store.set(cache_key_photo(sid), response.content, timeout=config["C1C_PHOTO_CACHE_LIFE"])
    return response.content, "image/jpeg"


# Input: sid, a student's ID number.
# Output: (SVG bytes, "image/svg+xml"), a plain head-and-shoulders drawing.
# Description: Stands in for a real photo in development and tests. The
# background color comes from the SID, so different students look different.
def fake_photo(sid: str) -> tuple[bytes, str]:
    hue = sum(map(ord, sid)) * 47 % 360
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
        f'<rect width="96" height="96" fill="hsl({hue} 45% 70%)"/>'
        '<circle cx="48" cy="38" r="18" fill="#fff"/>'
        '<ellipse cx="48" cy="92" rx="32" ry="28" fill="#fff"/>'
        "</svg>"
    )
    return svg.encode(), "image/svg+xml"
