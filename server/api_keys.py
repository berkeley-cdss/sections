"""Per-person API keys, scoped to one offering (#29).

A course admin makes a key on their course's Admin page. It's sent as
``Authorization: Bearer <key>`` to /offerings/<canvas course id>/api/sudo/<name>
and works only there, only while its owner is still an admin in that course,
and only as the owner or another member of the course.

Roles come from Canvas only when someone signs in, so a key also stops working
once its owner's last sign-in is older than API_KEY_ROLE_MAX_AGE; signing in
again picks up any role they've lost, and starts the key working again.
"""

import hashlib
import logging
import secrets
import sys
import threading
import time
from collections import defaultdict, deque

from flask import Flask, abort, current_app, g, request

from server.models import ApiKey, User, db
from server.offering import current_offering, get_course

KEY_PREFIX = "sections_"
# Long enough to tell keys apart in a list, short enough to give nothing away.
HINT_LENGTH = 4
DEFAULT_ROLE_MAX_AGE = 7 * 24 * 60 * 60
# Failed key attempts allowed from one client before it's refused for a while.
# Kept per server instance, which is enough to slow guessing of 256-bit keys.
DEFAULT_FAILURE_LIMIT = 10
DEFAULT_FAILURE_WINDOW = 15 * 60

# Every request made with a key is logged here. Its own handler, at INFO, so
# the log doesn't depend on how the app's logger is configured under gunicorn.
audit_log = logging.getLogger("sections.api_keys")
if not audit_log.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    audit_log.addHandler(_handler)
    audit_log.setLevel(logging.INFO)
    audit_log.propagate = False


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_key(owner: User, name: str) -> tuple[ApiKey, str]:
    """A new key for ``owner`` in the current offering, and the key itself,
    which isn't stored and can't be shown again."""
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    api_key = ApiKey(course=get_course(), owner=owner, name=name, key_hash=hash_key(key),
                     hint=key[-HINT_LENGTH:], created_at=int(time.time()))
    db.session.add(api_key)
    return api_key, key


def using_api_key() -> bool:
    """Whether this request was made with an API key rather than a signed-in browser."""
    return g.get("api_key") is not None


def client_address() -> str:
    # Cloud Run appends the client's address to X-Forwarded-For; anything
    # before it came from the client and can't be trusted.
    return request.access_route[-1] if request.access_route else (request.remote_addr or "")


class FailureLimiter:
    """Counts failed key attempts per client in a sliding window."""

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self.failures = defaultdict(deque)
        self.lock = threading.Lock()

    def _recent(self, client: str, now: float) -> deque:
        attempts = self.failures[client]
        while attempts and attempts[0] <= now - self.window:
            attempts.popleft()
        return attempts

    def is_limited(self, client: str) -> bool:
        with self.lock:
            return len(self._recent(client, time.monotonic())) >= self.limit

    def record(self, client: str):
        with self.lock:
            now = time.monotonic()
            self._recent(client, now).append(now)


def init_api_keys(app: Flask):
    app.extensions["api_key_failures"] = FailureLimiter(
        app.config.get("API_KEY_FAILURE_LIMIT", DEFAULT_FAILURE_LIMIT),
        app.config.get("API_KEY_FAILURE_WINDOW", DEFAULT_FAILURE_WINDOW),
    )


def _refuse(status: int, message: str, *, failed_attempt: bool):
    client = client_address()
    if failed_attempt:
        current_app.extensions["api_key_failures"].record(client)
    audit_log.warning("refused %s %s from %s: %s", request.method, request.path, client, message)
    abort(status, message)


def authenticate() -> ApiKey:
    """The key this request was made with, if it's valid for the current
    offering and its owner is still an admin there; otherwise abort."""
    limiter = current_app.extensions["api_key_failures"]
    if limiter.is_limited(client_address()):
        _refuse(429, "Too many failed API key attempts. Try again later.", failed_attempt=False)

    scheme, _, key = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not key.strip():
        _refuse(401, "Send your API key as \"Authorization: Bearer <key>\".", failed_attempt=True)
    api_key = ApiKey.query.filter_by(key_hash=hash_key(key.strip())).one_or_none()
    # A revoked key, or another course's, is refused like one that doesn't exist.
    if api_key is None or api_key.revoked_at is not None or api_key.course != get_course():
        _refuse(401, "That API key isn't valid for this course.", failed_attempt=True)

    owner = api_key.owner
    max_age = current_app.config.get("API_KEY_ROLE_MAX_AGE", DEFAULT_ROLE_MAX_AGE)
    synced_at = owner.canvas_synced_at
    if synced_at is None or time.time() - synced_at > max_age:
        _refuse(403, f"This API key's owner, {owner.email}, needs to sign in to Sections again "
                     "so their bCourses role can be checked.", failed_attempt=False)
    roles = owner.canvas_roles_in(current_offering().canvas_id)
    if not owner.is_global_admin and not (roles is not None and roles[1]):
        _refuse(403, f"This API key's owner, {owner.email}, is no longer an admin in this course.",
                failed_attempt=False)
    return api_key


def record_use(api_key: ApiKey, acting_as: User, endpoint: str):
    api_key.last_used_at = int(time.time())
    db.session.commit()
    audit_log.info("key %d (%r, owner %s) in %s called %s as %s from %s", api_key.id, api_key.name,
                   api_key.owner.email, api_key.course, endpoint, acting_as.email, client_address())
