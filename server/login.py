import time

import flask
from authlib.integrations.base_client import OAuthError
from authlib.integrations.flask_client import OAuth
from flask import abort, current_app, redirect, request, session, url_for
from flask_login import LoginManager, login_user, logout_user
from markupsafe import escape
from werkzeug.exceptions import HTTPException

from server import canvas_service
from server.canvas_tokens import LEGACY_SESSION_KEYS, discard_token, store_token
from server.errors import error_page, report_unexpected
from server.offering import current_offering, in_offering
from server.models import User, db, with_email

AFTER_LOGIN_KEY = "after_login"
# When the user last signed in through Canvas, in the (signed) session cookie.
SIGNED_IN_AT_KEY = "signed_in_at"
# Roles come from Canvas only at sign-in, so a sign-in older than this is
# refused and the user signs in again, picking up any role they've gained or
# lost. Overridable with the SIGN_IN_MAX_AGE config value, in seconds.
DEFAULT_SIGN_IN_MAX_AGE = 12 * 60 * 60


def _safe_next(target):
    # Only redirect back to paths on this site.
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


def sign_in_expired() -> bool:
    """Whether this session's sign-in is too old to trust its Canvas roles, or
    has no sign-in time (sessions and remember cookies from before it was kept)."""
    signed_in_at = session.get(SIGNED_IN_AT_KEY)
    max_age = current_app.config.get("SIGN_IN_MAX_AGE", DEFAULT_SIGN_IN_MAX_AGE)
    return not isinstance(signed_in_at, (int, float)) or time.time() - signed_in_at > max_age


def complete_login(token: dict):
    """Create or update the signed-in User from a Canvas OAuth token response."""
    canvas_user_id = str(token["user"]["id"])
    access_token = token["access_token"]
    profile = canvas_service.get_profile(canvas_user_id, access_token)
    email = profile.get("primary_email") or profile.get("login_id")
    name = profile.get("short_name") or profile.get("name") or email
    courses = canvas_service.get_user_courses(canvas_user_id, access_token)
    override_id = current_app.config.get("ADMIN_OVERRIDE_CANVAS_COURSE_ID")

    # Canvas ids are stable; emails can change, so they're only used to claim
    # someone added by staff or imported from a spreadsheet who hasn't logged in.
    user = User.query.filter_by(canvas_id=canvas_user_id).one_or_none()
    email_owner = with_email(email)
    if user is None:
        if email_owner is not None and email_owner.canvas_id is not None:
            abort(403, f"{email} already belongs to a different bCourses account. "
                       "Contact the course staff.")
        user = email_owner or User(email=email)
        db.session.add(user)
        user.canvas_id = canvas_user_id
    elif email_owner is not None and email_owner is not user:
        if email_owner.canvas_id is None:
            # The same person, imported under their new email: merge them.
            user.absorb(email_owner)
        else:
            # Another bCourses account has this email; keep the one we have.
            email = user.email
    user.email = email
    user.name = name
    user.pronouns = profile.get("pronouns") or None
    user.canvas_courses = courses
    user.is_global_admin = override_id is not None and str(override_id) in courses
    user.canvas_synced_at = int(time.time())
    db.session.commit()

    # No remember cookie: it holds no time, so it would sign the user back in
    # with roles from their last sign-in for as long as the browser keeps it.
    login_user(user)
    session.permanent = True
    session[SIGNED_IN_AT_KEY] = time.time()
    # Keep the short-lived access token, on the server, only for staff, who
    # need it to look up students; they sign in again when it expires. Any
    # token from this browser's previous sign-in is revoked.
    discard_token()
    if user.is_global_admin or any(c["is_staff"] for c in courses.values()):
        store_token(user, access_token, token.get("expires_in", 3600))


def finish_login(token: dict):
    """Sign in with a Canvas OAuth token response, then go back to the page that
    sent the user to log in."""
    try:
        complete_login(token)
    except HTTPException:
        raise  # already says what's wrong, e.g. an email that belongs to another account
    except Exception as error:
        db.session.rollback()
        message = report_unexpected(error, "saving your account")
        return error_page("Couldn't sign you in", f"bCourses signed you in, but Sections couldn't. {message}", 500)
    return redirect(session.pop(AFTER_LOGIN_KEY, None) or url_for("offerings"))


def sync_offering_role(user: User) -> bool:
    """Bring the user's role in the current offering in line with Canvas.

    Returns False if the user isn't enrolled in the offering's Canvas course.
    """
    if user.is_global_admin:
        return True
    offering = current_offering()
    roles = user.canvas_roles_in(offering.canvas_id)
    if roles is None:
        return False
    is_staff, is_admin = roles
    if (offering.key in user.staff_offerings, offering.key in user.admin_offerings,
            user.is_member_of(offering.key)) != (is_staff, is_admin, True):
        user.set_role(offering.key, is_staff=is_staff, is_admin=is_admin)
        db.session.commit()
    return True


def create_login_client(app: flask.Flask):
    login_manager = LoginManager()
    login_manager.init_app(app)

    oauth = OAuth(app)
    canvas_server_url = app.config["CANVAS_SERVER_URL"]
    canvas = oauth.register(
        "canvas",
        client_id=app.config["CANVAS_CLIENT_ID"],
        client_secret=app.config["CANVAS_CLIENT_SECRET"],
        access_token_url=canvas_server_url + "login/oauth2/token",
        authorize_url=canvas_server_url + "login/oauth2/auth",
        client_kwargs={
            "scope": " ".join(canvas_service.SCOPES),
            # Canvas expects the client credentials in the POST body.
            "token_endpoint_auth_method": "client_secret_post",
        },
    )

    @login_manager.user_loader
    def load_user(session_id):
        user_id = User.parse_session_id(session_id)
        if user_id is None or sign_in_expired():
            return None
        user = db.session.get(User, user_id)
        if user is not None and in_offering() and not sync_offering_role(user):
            # Sign-in only reads active enrollments, so someone just added to the
            # course must accept the bCourses invitation before signing in again.
            abort(403, "You aren't enrolled in this course on bCourses. If you were just added, "
                       "accept the invitation in bCourses, then log out of Sections and sign in again.")
        return user

    @login_manager.unauthorized_handler
    def unauthorized():
        # The course pages' API calls expect a 401; pages go to the login page.
        if "/api/" in request.path:
            abort(401)
        return redirect(url_for("login", next=request.full_path.rstrip("?")))

    # Same routes as seating.
    @app.route("/login/")
    def login():
        session[AFTER_LOGIN_KEY] = _safe_next(request.args.get("next"))
        if canvas_service.is_mock_canvas():
            return redirect(url_for("dev_login"))
        return canvas.authorize_redirect(url_for("authorized", _external=True))

    @app.route("/authorized/")
    def authorized():
        try:
            token = canvas.authorize_access_token()
        except OAuthError as e:
            # The error is copied from the `error`/`error_description` query parameters, which anyone
            # can put in a link, and a returned str is served as HTML: escape it.
            return f"Access denied: {escape(e.description or e.error or 'unknown error')}", 403
        return finish_login(token)

    @app.before_request
    def drop_token_from_cookie():
        # Canvas tokens used to be kept in the session cookie itself.
        for key in LEGACY_SESSION_KEYS:
            session.pop(key, None)

    # A POST, so the cross-origin check covers it and other sites can't sign users out.
    @app.route("/logout/", methods=["POST"])
    def logout():
        session.pop(SIGNED_IN_AT_KEY, None)
        discard_token()
        logout_user()
        return redirect(url_for("index"))
