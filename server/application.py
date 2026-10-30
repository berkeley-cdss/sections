import os

from flask import Flask
from flask_migrate import Migrate
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.middleware.proxy_fix import ProxyFix

from config import load_config
from dev_login import create_dev_login_page
from errors import register_error_handlers
from offerings import create_offering_pages
from login import create_login_client
from models import db
from schema_check import check_schema_before_requests
from security_headers import add_security_headers
from state import create_state_client

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(SERVER_DIR, "templates")
# Schema changes are Alembic migrations here; `flask db upgrade` applies them.
MIGRATIONS_DIR = os.path.join(SERVER_DIR, "migrations")


def create_app(test_config: dict | None = None) -> Flask:
    """The Sections app, configured from the environment (see config.py), or
    from ``test_config`` alone in tests."""
    app = Flask(
        __name__, static_url_path="", static_folder="static", template_folder="static"
    )
    app.url_map.strict_slashes = False
    # Offering pages are the React build in static/; server-rendered pages live in templates/.
    # static/ is searched first, so templates/ must not reuse the build's names (hence landing.html,
    # not index.html). Name templates *.html so that Flask autoescapes them.
    app.jinja_loader = ChoiceLoader([app.jinja_loader, FileSystemLoader(TEMPLATES_DIR)])
    # Cloud Run terminates TLS, so trust its X-Forwarded-Proto for external URLs.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    if test_config is None:
        load_config(app)
    else:
        app.config.update(test_config)
    db.init_app(app)
    Migrate(app, db, directory=MIGRATIONS_DIR)
    create_state_client(app)
    create_login_client(app)
    create_dev_login_page(app)
    create_offering_pages(app)
    add_security_headers(app)
    register_error_handlers(app)
    # Test apps build their tables with create_all rather than migrations, so
    # their databases have no migration to check. test_schema_check tests it.
    if test_config is None:
        check_schema_before_requests(app, MIGRATIONS_DIR)

    @app.route("/health")
    def health():
        return "ok"

    return app
