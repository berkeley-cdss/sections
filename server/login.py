import time

import flask
from authlib.integrations.base_client import OAuthError
from authlib.integrations.flask_client import OAuth
from flask import abort, current_app, redirect, request, session, url_for
from flask_login import LoginManager, login_user, logout_user
from markupsafe import escape

import canvas_service
from course import current_course, get_course, in_course
from models import Account, User, db

AFTER_LOGIN_KEY = "after_login"


def _safe_next(target):
    # Only redirect back to paths on this site.
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


def complete_login(token: dict):
    """Create or update the signed-in Account from a Canvas OAuth token response."""
    canvas_user_id = token["user"]["id"]
    access_token = token["access_token"]
    profile = canvas_service.get_profile(canvas_user_id, access_token)
    email = profile.get("primary_email") or profile.get("login_id")
    name = profile.get("short_name") or profile.get("name") or email
    courses = canvas_service.get_user_courses(canvas_user_id, access_token)
    override_id = current_app.config.get("ADMIN_OVERRIDE_CANVAS_COURSE_ID")

    account = Account.query.filter_by(canvas_id=str(canvas_user_id)).one_or_none()
    if account is None:
        account = Account(canvas_id=str(canvas_user_id))
        db.session.add(account)
    account.email = email
    account.name = name
    account.canvas_courses = courses
    account.is_global_admin = override_id is not None and str(override_id) in courses
    db.session.commit()

    login_user(account, remember=True)
    session.permanent = True
    # Keep only a short-lived access token, and only for staff, who need it to
    # look up students; reauthorize when it expires.
    session.pop("canvas_access_token", None)
    session.pop("canvas_token_expires_at", None)
    if account.is_global_admin or any(c["is_staff"] for c in courses.values()):
        session["canvas_access_token"] = access_token
        session["canvas_token_expires_at"] = time.time() + token.get("expires_in", 3600)


def course_user(account: Account):
    """The account's User row in the current course, created on first visit.

    Staff and admin flags follow the account's Canvas roles from its last
    sign-in. Returns None if the account isn't enrolled in the course.
    """
    roles = account.roles_in(current_course().canvas_id)
    if roles is None:
        return None
    is_staff, is_admin = roles
    course = get_course()
    user = User.query.filter_by(email=account.email, course=course).one_or_none()
    if user is None:
        user = User(email=account.email, name=account.name, is_staff=is_staff,
                    is_admin=is_admin, course=course)
        db.session.add(user)
    elif (user.name, user.is_staff, user.is_admin) == (account.name, is_staff, is_admin):
        return user
    user.name = account.name
    user.is_staff = is_staff
    user.is_admin = is_admin
    db.session.commit()
    return user


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
        account_id = Account.parse_session_id(session_id)
        account = db.session.get(Account, account_id) if account_id else None
        if account is None or not in_course():
            return account
        user = course_user(account)
        if user is None:
            abort(403, "You aren't enrolled in this course on bCourses. If you just "
                       "enrolled, sign out and sign in again.")
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
        return canvas.authorize_redirect(url_for("authorized", _external=True))

    @app.route("/authorized/")
    def authorized():
        try:
            token = canvas.authorize_access_token()
        except OAuthError as e:
            return f"Access denied: {escape(e.description or e.error)}", 403
        complete_login(token)
        return redirect(session.pop(AFTER_LOGIN_KEY, None) or url_for("offerings"))

    @app.route("/logout/")
    def logout():
        session.pop("canvas_access_token", None)
        session.pop("canvas_token_expires_at", None)
        logout_user()
        return redirect(url_for("index"))
