"""Error responses that say what went wrong, instead of Flask's default
"Internal Server Error" page or an HTML page the course pages can't read.

Course API calls (paths containing /api/) get JSON in the same shape as a
Failure, {"success": false, "message": ...}, which the course pages show as an
error message. Other pages get error.html. An unexpected error gets a reference
ID, logged with its traceback, so a report leads straight to the log entry.
"""

import uuid
from datetime import datetime, timezone

import flask
from flask import current_app, jsonify, request
from sqlalchemy.exc import NoResultFound
from werkzeug.exceptions import HTTPException

from models import db

API_MESSAGES = {
    401: "You've been signed out. Reload the page to sign in again.",
}


def is_api_request() -> bool:
    return "/api/" in request.path


def error_reference() -> str:
    """Cloud Run's trace ID for this request, which Cloud Logging shows with
    the request's log entries, or a random ID elsewhere."""
    trace = request.headers.get("X-Cloud-Trace-Context", "").split("/")[0]
    return trace or uuid.uuid4().hex[:12]


def shows_details() -> bool:
    """Show exceptions on staging and in development, never in production,
    where they could expose the schema. Unset counts as production."""
    return current_app.config.get("APP_ENV") in ("staging", "development")


def report_unexpected(error: Exception, doing: str) -> str:
    """Log ``error`` with a new reference and return a message for the user,
    who was ``doing`` something (e.g. "saving your changes")."""
    reference = error_reference()
    current_app.logger.exception("Unexpected error (reference %s)", reference, exc_info=error)
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    message = (
        f"Something went wrong on the Sections server while {doing}. If it keeps happening, "
        f"report it with reference {reference} ({when})."
    )
    if shows_details():
        message += f" Details: {type(error).__name__}: {error}"
    return message


def error_page(title: str, message: str, status: int):
    # Rendered without render_template, whose context processors include
    # Flask-Login's, which loads the signed-in user from the database: that may
    # be what failed. error.html doesn't show the user either.
    template = current_app.jinja_env.get_template("error.html")
    return template.render(title=title, message=message), status


def register_error_handlers(app: flask.Flask):
    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        if is_api_request():
            message = API_MESSAGES.get(error.code, error.description)
            return jsonify({"success": False, "message": message}), error.code
        return error_page(f"{error.code} {error.name}", error.description, error.code)

    @app.errorhandler(Exception)
    def unexpected_error(error: Exception):
        # Leave the session usable for anything that runs after this.
        db.session.rollback()
        if isinstance(error, NoResultFound):
            # Most often a section or session that someone else deleted.
            message = "That item no longer exists; it may have been deleted. Reload the page and try again."
            status = 404
        else:
            doing = "handling your request" if is_api_request() else "loading this page"
            message = report_unexpected(error, doing)
            status = 500
        if is_api_request():
            return jsonify({"success": False, "message": message}), status
        return error_page("Something went wrong", message, status)
