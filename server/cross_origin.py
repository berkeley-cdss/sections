"""Refuse form posts and API calls that another site made a signed-in browser send.

The session cookie is SameSite=Lax, which stops other *sites* from sending it
with a post but not other *origins* on the same site: if Sections were served
from a subdomain of berkeley.edu, a page on any other berkeley.edu subdomain
could post a form to Sections with the user's cookie attached. Browsers say who
made a request in Sec-Fetch-Site and Origin, which pages can't set, so a
request that changes something is refused unless they say it came from
Sections itself. This is the check Go's http.CrossOriginProtection makes; it
needs no token in each form.

A request with neither header didn't come from a browser (or came from one
too old to send them), so it carries no cookie a page elsewhere could borrow,
and is let through.
"""

import flask
from flask import abort, request

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
MESSAGE = ("This request came from another website, so Sections refused it. "
           "Go back to Sections and try again from there.")


def is_cross_origin() -> bool:
    fetch_site = request.headers.get("Sec-Fetch-Site")
    if fetch_site is not None:
        # "none" is a request the user made directly, e.g. from a bookmark.
        return fetch_site not in ("same-origin", "none")
    origin = request.headers.get("Origin")
    if origin is None:
        return False
    # ProxyFix makes request.scheme https behind Cloud Run.
    return origin != f"{request.scheme}://{request.host}"


def refuse_cross_origin_requests(app: flask.Flask):
    @app.before_request
    def check_origin():
        if request.method not in SAFE_METHODS and is_cross_origin():
            abort(403, MESSAGE)
