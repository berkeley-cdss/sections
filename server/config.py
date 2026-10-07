import os
import re

import flask
from dotenv import load_dotenv

DEV_SQLITE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "app.db")


def _cloud_sql_creator(instance: str, user: str, db: str):
    """Connect to Cloud SQL with IAM database authentication, so no password is stored.

    Cloud Run's built-in /cloudsql socket can't do IAM login, hence the connector.
    """
    from google.cloud.sql.connector import Connector

    # Lazy refresh suits Cloud Run, where CPU is throttled between requests.
    connector = Connector(refresh_strategy="lazy")
    return lambda: connector.connect(instance, "pg8000", user=user, db=db, enable_iam_auth=True)


def _database_config(is_dev: bool) -> dict:
    """SQLAlchemy URI and engine options.

    In order of precedence: Cloud SQL with IAM auth (CLOUD_SQL_INSTANCE, DB_USER,
    DB_NAME), then DATABASE_URL, then a local SQLite file in development.
    """
    engine_options = {"pool_pre_ping": True}
    instance = os.getenv("CLOUD_SQL_INSTANCE")
    if instance:
        engine_options["creator"] = _cloud_sql_creator(instance, _require("DB_USER"), _require("DB_NAME"))
        return dict(SQLALCHEMY_DATABASE_URI="postgresql+pg8000://", SQLALCHEMY_ENGINE_OPTIONS=engine_options)
    url = os.getenv("DATABASE_URL")
    if url:
        # Cloud SQL / Heroku style URLs don't name a driver.
        url = re.sub(r"^postgres(ql)?://", "postgresql+psycopg2://", url)
    elif is_dev:
        url = "sqlite:///" + DEV_SQLITE_PATH
    else:
        raise RuntimeError("Set CLOUD_SQL_INSTANCE or DATABASE_URL outside development")
    return dict(SQLALCHEMY_DATABASE_URI=url, SQLALCHEMY_ENGINE_OPTIONS=engine_options)


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Environment variable {key} must be set")
    return value


def load_config(app: flask.Flask):
    """Load app config from the environment (and a local .env file, if present).

    FLASK_ENV is one of development, staging, production, matching seating. It
    is required so a misconfigured deployment can't fall back to development
    settings (SQLite, a fixed SECRET_KEY).
    """
    load_dotenv()
    env = _require("FLASK_ENV").lower()
    if env not in ("development", "staging", "production"):
        raise RuntimeError(f"FLASK_ENV must be development, staging or production, not {env!r}")
    is_dev = env == "development"

    canvas_server_url = _require("CANVAS_SERVER_URL")
    admin_override = os.getenv("ADMIN_OVERRIDE_CANVAS_COURSE_ID")

    app.config.update(
        APP_ENV=env,
        SECRET_KEY=os.getenv("SECRET_KEY") or ("development" if is_dev else _require("SECRET_KEY")),
        **_database_config(is_dev),
        CANVAS_SERVER_URL=canvas_server_url.rstrip("/") + "/",
        CANVAS_CLIENT_ID=_require("CANVAS_CLIENT_ID"),
        CANVAS_CLIENT_SECRET=_require("CANVAS_CLIENT_SECRET"),
        # Members of this bCourses course are staff and admin in every course.
        ADMIN_OVERRIDE_CANVAS_COURSE_ID=int(admin_override) if admin_override else None,
        # Shown to staff as the account to share import spreadsheets with.
        GOOGLE_SERVICE_ACCOUNT_EMAIL=os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL"),
        # Shared secret for the /api/sudo/* and export_attendance_secret endpoints.
        API_SECRET=os.getenv("API_SECRET"),
        PERMANENT_SESSION_LIFETIME=7200,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=not is_dev,
        SESSION_COOKIE_SAMESITE="Lax",
    )
