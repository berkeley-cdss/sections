"""Staff's Canvas access tokens, kept on the server rather than in the session cookie.

Staff need a Canvas token to look up students who haven't signed in to Sections
yet (add_students). Flask's session cookie is signed but not encrypted, so a
token kept there could be read by anyone holding a copy of the cookie, and that
copy would keep working after logout until the token expired. Instead the cookie
holds a random handle for a CanvasToken row. Signing out, or in again, deletes
the row and revokes the token with Canvas, so no copy of the cookie can use it.
"""

import hashlib
import secrets
import time

from flask import session

from server import canvas_service
from server.models import CanvasToken, User, db

SESSION_KEY = "canvas_token_id"
# Where tokens were kept in the cookie before this; dropped wherever they're found.
LEGACY_SESSION_KEYS = ("canvas_access_token", "canvas_token_expires_at")
# Treat a token this close to expiring as expired, so a lookup doesn't fail halfway.
EXPIRY_MARGIN = 60


def _hash(handle: str) -> str:
    return hashlib.sha256(handle.encode()).hexdigest()


def _this_browsers_row() -> CanvasToken | None:
    handle = session.get(SESSION_KEY)
    if not isinstance(handle, str):
        return None
    return CanvasToken.query.filter_by(handle_hash=_hash(handle)).one_or_none()


def store_token(user: User, access_token: str, expires_in: float):
    """Keep ``access_token`` for this browser's sign-in as ``user``."""
    now = time.time()
    handle = secrets.token_urlsafe(32)
    db.session.add(CanvasToken(user_id=user.id, handle_hash=_hash(handle), access_token=access_token,
                               expires_at=int(now + expires_in)))
    # Tokens from sign-ins that never signed out; Canvas no longer accepts them.
    CanvasToken.query.filter(CanvasToken.expires_at < now).delete()
    db.session.commit()
    session[SESSION_KEY] = handle


def current_token(user: User) -> str | None:
    """This browser's Canvas token for ``user``, or None if there's none or it has
    (nearly) expired, in which case they need to sign in again."""
    row = _this_browsers_row()
    if row is None or row.user_id != user.id or time.time() + EXPIRY_MARGIN >= row.expires_at:
        return None
    return row.access_token


def discard_token():
    """Forget this browser's token, and revoke it with Canvas."""
    row = _this_browsers_row()
    session.pop(SESSION_KEY, None)
    for key in LEGACY_SESSION_KEYS:
        session.pop(key, None)
    if row is None:
        return
    access_token, expired = row.access_token, row.expires_at <= time.time()
    db.session.delete(row)
    db.session.commit()
    if not expired:
        canvas_service.revoke_token(access_token)
