"""Student photos from the Cal 1 Card office's API (C1C), for roster photos (#4).

Works like seating's server/services/c1c/__init__.py, which has used this API
since 2024, and takes the same settings. C1C only answers requests from
allowlisted addresses, so requests go through C1C_PROXY_URL when it's set.
"""

import requests
from flask import current_app

# Seconds to wait for C1C, so a slow response can't hold up the request; the
# roster shows the placeholder instead.
TIMEOUT = 10


# Input: sid, a student's ID number.
# Output: (image bytes, content type), or None if there's no photo.
# Description: Development uses a made-up picture (fake_photo) unless
# MOCK_C1C=false. Without C1C settings (as on staging today), or if C1C fails,
# there's no photo, so the page shows a placeholder instead of an error.
def get_photo(sid: str) -> tuple[bytes, str] | None:
    config = current_app.config
    if config.get("MOCK_C1C"):
        return fake_photo(sid)
    if not config.get("C1C_API_DOMAIN"):
        return None
    proxy_url = config.get("C1C_PROXY_URL")
    try:
        response = requests.get(
            config["C1C_API_DOMAIN"].rstrip("/") + f"/c1c-api/v1/photo/{sid}",
            auth=(config["C1C_API_USERNAME"], config["C1C_API_PASSWORD"]),
            proxies={"http": proxy_url, "https": proxy_url} if proxy_url else None,
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
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
