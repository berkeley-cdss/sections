"""Errors should say what went wrong (issue #7): course API calls get a JSON
message the course pages can show, other pages get a Sections error page, and an
unexpected error gets a reference to find it in the logs."""

import unittest
from unittest.mock import patch

from authlib.integrations.flask_client import FlaskOAuth2App
from flask import Flask, g

from errors import register_error_handlers
from login import create_login_client
from models import CourseConfig, Offering, Section, User, db
from offerings import create_offering_pages
from state import create_state_client

CS61A = 101


class ErrorTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SECRET_KEY="test", TESTING=True,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            CANVAS_SERVER_URL="https://canvas.test/",
            CANVAS_CLIENT_ID="id", CANVAS_CLIENT_SECRET="secret",
        )
        db.init_app(self.app)
        create_state_client(self.app)
        create_login_client(self.app)
        create_offering_pages(self.app)
        register_error_handlers(self.app)

        @self.app.route("/offerings/<int:canvas_course_id>/api/explode", methods=["POST"])
        @self.app.route("/explode")
        def explode(**_):
            raise RuntimeError("column users.pronouns does not exist")

        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        admin = User(email="admin@test", name="Admin", canvas_id="1", canvas_courses={str(CS61A): {
            "name": "CS 61A", "code": "CS 61A", "start_at": None,
            "is_staff": True, "is_admin": True, "is_student": False}})
        admin.set_role("cs61a", is_staff=True, is_admin=True)
        section = Section(course="cs61a", name="Lab", location="Room", description="", capacity=30,
                          can_self_enroll=True, start_time=0, end_time=3600)
        db.session.add_all([Offering(canvas_id=CS61A, key="cs61a", name="CS 61A"), admin, section,
                            CourseConfig(course="cs61a")])
        db.session.commit()
        self.admin, self.section_id = admin, section.id
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def sign_in(self):
        with self.client.session_transaction() as browser:
            browser["_user_id"] = self.admin.get_id()

    def request(self, method, path, **kwargs):
        # The test's app context is reused for requests; see test_canvas_login.
        for key in ("offering", "_login_user"):
            g.pop(key, None)
        return getattr(self.client, method)(path, **kwargs)

    def api(self, method, canvas_course_id=CS61A, headers=None, **args):
        return self.request("post", f"/offerings/{canvas_course_id}/api/{method}", json=args, headers=headers)

    def test_unexpected_api_errors_give_a_reference_and_hide_details_in_production(self):
        response = self.api("explode", headers={"X-Cloud-Trace-Context": "abc123/1;o=1"})
        self.assertEqual(response.status_code, 500)
        body = response.get_json()
        self.assertFalse(body["success"])
        self.assertIn("reference abc123", body["message"])
        self.assertNotIn("pronouns", body["message"])

    def test_staging_shows_the_exception(self):
        self.app.config["APP_ENV"] = "staging"
        message = self.api("explode").get_json()["message"]
        self.assertIn("RuntimeError: column users.pronouns does not exist", message)

    def test_unexpected_page_errors_render_a_sections_page(self):
        with self.assertLogs(self.app.logger, "ERROR") as logs:
            response = self.request("get", "/explode", headers={"X-Cloud-Trace-Context": "abc123/1"})
        self.assertEqual(response.status_code, 500)
        page = response.get_data(as_text=True)
        self.assertIn("Something went wrong on the Sections server while loading this page", page)
        self.assertIn("reference abc123", page)
        self.assertIn("Back to Sections", page)
        # The log entry has the same reference and the traceback.
        self.assertIn("abc123", logs.output[0])
        self.assertIn("RuntimeError", logs.output[0])

    def test_error_page_works_when_the_database_does_not(self):
        # Like a preview one migration behind: loading the signed-in user fails.
        self.sign_in()
        with patch.object(User, "parse_session_id", side_effect=RuntimeError("database is down")), \
                self.assertLogs(self.app.logger, "ERROR"):
            response = self.request("get", "/offerings")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Something went wrong on the Sections server", response.get_data(as_text=True))

    def test_signed_out_api_calls_say_so(self):
        # refresh_state works signed out; this needs a signed-in user.
        response = self.api("update_section_description", section_id=str(self.section_id), description="Hi")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {
            "success": False, "message": "You've been signed out. Reload the page to sign in again."})

    def test_courses_that_are_not_set_up_say_so(self):
        self.sign_in()
        message = self.api("refresh_state", canvas_course_id=999).get_json()["message"]
        self.assertIn("Sections isn't set up for this course yet", message)
        page = self.request("get", "/offerings/999/").get_data(as_text=True)
        self.assertIn("Sections isn&#39;t set up for this course yet", page)

    def test_deleted_items_say_so(self):
        self.sign_in()
        response = self.api("update_section_description", section_id="999", description="Hi")
        self.assertEqual(response.status_code, 404)
        self.assertIn("no longer exists", response.get_json()["message"])

    def test_text_longer_than_its_column_is_rejected_by_name(self):
        self.sign_in()
        section_id = str(self.section_id)
        cases = [
            ("update_section_description", {"description": "x" * 256}, "Your introduction must be at most 255"),
            ("update_section_call_link", {"call_link": "x" * 256}, "The call link must be at most 255"),
            ("update_section_enrollment_code", {"enrollment_code": "x" * 256},
             "The enrollment code must be at most 255"),
            ("update_section_location", {"new_location": "x" * 256}, "Location must be at most 255"),
            ("update_section_tags", {"tags": "a," * 128}, "Tags must be at most 255 characters, but it's 256."),
        ]
        for method, args, message in cases:
            with self.subTest(method=method):
                body = self.api(method, section_id=section_id, **args).get_json()
                self.assertFalse(body["success"])
                self.assertIn(message, body["message"])
        body = self.api("update_config", message="x" * 1025).get_json()
        self.assertIn("The welcome message must be at most 1024", body["message"])
        # At the limit is fine.
        self.assertTrue(self.api("update_section_description", section_id=section_id,
                                 description="x" * 255).get_json()["success"])

    def test_login_failures_after_bcourses_say_which_side_failed(self):
        token = {"user": {"id": 1}, "access_token": "access"}
        with patch.object(FlaskOAuth2App, "authorize_access_token", return_value=token), \
                patch("login.complete_login", side_effect=RuntimeError("database is down")), \
                self.assertLogs(self.app.logger, "ERROR"):
            response = self.request("get", "/authorized/")
        self.assertEqual(response.status_code, 500)
        page = response.get_data(as_text=True)
        self.assertIn("bCourses signed you in, but Sections couldn&#39;t.", page)
        self.assertIn("while saving your account", page)


if __name__ == "__main__":
    unittest.main()
