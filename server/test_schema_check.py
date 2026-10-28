"""Requests are refused, with a reason, while the database's migrations don't
match the code's: most often a PR preview whose PR adds a migration (#7)."""

import os
import tempfile
import unittest
from unittest.mock import patch

import sqlalchemy as sa
from alembic.script import ScriptDirectory
from flask import Flask
from flask_migrate import Migrate, upgrade

from errors import register_error_handlers
from models import db
from offerings import create_offering_pages
from schema_check import check_schema_before_requests

MIGRATIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
HEAD = ScriptDirectory(MIGRATIONS).get_current_head()


class SchemaCheckTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.app = Flask(__name__)
        self.app.config.update(SECRET_KEY="test", TESTING=True,
                               SQLALCHEMY_DATABASE_URI=f"sqlite:///{self.path}")
        db.init_app(self.app)
        Migrate(self.app, db, directory=MIGRATIONS)
        # The error page links the pages' stylesheets and the index.
        create_offering_pages(self.app)
        register_error_handlers(self.app)
        check_schema_before_requests(self.app, MIGRATIONS)
        self.app.add_url_rule("/health", "health", lambda: "ok")
        self.app.add_url_rule("/page", "page", lambda: "page")
        self.app.add_url_rule("/offerings/1/api/refresh_state", "api", lambda: {"success": True},
                              methods=["POST"])
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        os.remove(self.path)

    def set_revision(self, revision):
        with db.engine.begin() as connection:
            connection.execute(sa.text("UPDATE alembic_version SET version_num = :rev"), {"rev": revision})

    def test_matching_schema_serves_requests(self):
        upgrade()
        self.assertEqual(self.client.get("/health").get_data(as_text=True), "ok")
        self.assertEqual(self.client.get("/page").status_code, 200)

    def test_preview_of_a_pr_with_a_migration_says_to_merge(self):
        upgrade(revision="0003_schema_cleanup")
        with patch.dict(os.environ, {"PREVIEW_PR": "42"}):
            response = self.client.post("/offerings/1/api/refresh_state", json={})
        self.assertEqual(response.status_code, 503)
        message = response.get_json()["message"]
        self.assertIn(f"This is a preview of PR #42, which adds a database migration ({HEAD}).", message)
        self.assertIn("Merge the PR to see its changes on staging.", message)

    def test_pages_and_health_are_refused_too(self):
        upgrade(revision="0003_schema_cleanup")
        with patch.dict(os.environ, {"PREVIEW_PR": "42"}):
            page = self.client.get("/page")
            health = self.client.get("/health")
        self.assertEqual(page.status_code, 503)
        self.assertIn("This is a preview of PR #42", page.get_data(as_text=True))
        self.assertIn("Database migration needed", page.get_data(as_text=True))
        self.assertEqual(health.status_code, 503)
        # The error page's own stylesheet still loads.
        self.assertEqual(self.client.get("/assets/css/style.css").status_code, 200)

    def test_preview_older_than_the_database_says_to_merge_main(self):
        upgrade()
        self.set_revision("0099_from_main")
        with patch.dict(os.environ, {"PREVIEW_PR": "42"}):
            message = self.client.post("/offerings/1/api/refresh_state", json={}).get_json()["message"]
        self.assertIn("whose branch is older than the staging database (at migration 0099_from_main)", message)
        self.assertIn("Merge main into the PR's branch", message)

    def test_outside_previews_says_to_upgrade(self):
        upgrade(revision="0003_schema_cleanup")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PREVIEW_PR", None)
            message = self.client.post("/offerings/1/api/refresh_state", json={}).get_json()["message"]
        self.assertIn(f"The database is at migration 0003_schema_cleanup, but this version of Sections "
                      f"expects {HEAD}. Run `flask --app main db upgrade`", message)

    def test_result_is_cached_briefly(self):
        upgrade(revision="0003_schema_cleanup")
        self.assertEqual(self.client.get("/page").status_code, 503)
        upgrade()
        # Still the cached result...
        self.assertEqual(self.client.get("/page").status_code, 503)
        # ...until it expires.
        with patch("schema_check.time.monotonic", return_value=10**9):
            self.assertEqual(self.client.get("/page").status_code, 200)


if __name__ == "__main__":
    unittest.main()
