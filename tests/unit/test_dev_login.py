"""The fake Canvas and the /dev_login/ page that signs in to it, as in seating's
test_dev_login.py and test_mock_canvas_oauth.py."""

import os
import unittest
from unittest import mock

from flask import Flask

import canvas_service
from config import load_config
from dev_login import mock_user_roster
from models import Offering, User, db
from offering import load_offering
from tests.unit.support import AppTestCase, lab

ENV = {"FLASK_ENV": "development", "SECRET_KEY": "test", "DATABASE_URL": "sqlite:///:memory:"}
CANVAS_ENV = {"CANVAS_SERVER_URL": "https://canvas.test/", "CANVAS_CLIENT_ID": "id",
              "CANVAS_CLIENT_SECRET": "secret"}
# Seeded users (server/fake_canvas_data): a TA, a student and a teacher in CS 169A.
YU_LONG, JIMMY_XU, OSKI = "123456", "234567", "567890"
CS169A = 1234567


def configured(**overrides):
    """The app's config, as load_config reads it from exactly ENV and these variables."""
    env = {**ENV, **overrides}
    app = Flask(__name__)
    # Ignore a developer's own .env.
    with mock.patch.dict(os.environ, env, clear=True), mock.patch("config.load_dotenv"):
        load_config(app)
    return app.config


class EnvironmentGatingTests(unittest.TestCase):
    """The fake Canvas - and with it the dev login page - is the default in
    development, and must never be used in staging or production."""

    def test_development_mocks_canvas_without_canvas_credentials(self):
        self.assertIs(configured()["MOCK_CANVAS"], True)

    def test_development_can_opt_out_of_the_fake_canvas(self):
        config = configured(**CANVAS_ENV, MOCK_CANVAS="false")
        self.assertIs(config["MOCK_CANVAS"], False)
        # ...and then needs the Canvas credentials again.
        with self.assertRaises(RuntimeError):
            configured(MOCK_CANVAS="false")

    def test_staging_and_production_never_mock_canvas(self):
        for env in ("staging", "production"):
            with self.subTest(env=env):
                self.assertIs(configured(**CANVAS_ENV, FLASK_ENV=env, MOCK_CANVAS="true")["MOCK_CANVAS"], False)
                with self.assertRaises(RuntimeError):
                    configured(FLASK_ENV=env, MOCK_CANVAS="true")


class MockUserRosterTests(unittest.TestCase):
    def test_lists_the_seeded_users_by_name(self):
        self.assertEqual([user["name"] for user in mock_user_roster()],
                         ["Jimmy Xu", "Lavender Angela", "Oski Bear", "Sharon Lovera", "Yu Long"])

    def test_shows_the_roles_that_decide_what_a_user_can_do(self):
        yu_long = next(u for u in mock_user_roster() if u["name"] == "Yu Long")
        self.assertEqual((yu_long["id"], yu_long["email"]), (YU_LONG, "long_yu@berkeley.edu"))
        roles = {course["name"]: course["roles"] for course in yu_long["courses"]}
        self.assertEqual(roles["Introduction to Software Engineering (Fall 2023)"], ["ta"])
        self.assertEqual(roles["Computer Architecture (Fall 2022)"], ["student"])


class FakeCanvasTests(AppTestCase):
    """canvas_service answers from the fake Canvas as it would from bCourses."""

    config = {"MOCK_CANVAS": True}

    def test_profile(self):
        with self.app.test_request_context():
            profile = canvas_service.get_profile(YU_LONG, "dev_access_token")
        self.assertEqual((profile["primary_email"], profile["short_name"]), ("long_yu@berkeley.edu", "Yu Long"))

    def test_user_courses_and_roles(self):
        with self.app.test_request_context():
            courses = canvas_service.get_user_courses(OSKI, "dev_access_token")
            self.assertEqual(courses, {str(CS169A): {
                "name": "Introduction to Software Engineering (Fall 2023)", "code": "COMPSCI 169A",
                "start_at": "2023-08-16T07:00:00Z", "is_staff": True, "is_admin": True, "is_student": False,
            }})
            courses = canvas_service.get_user_courses(YU_LONG, "dev_access_token")
        self.assertEqual({c: (i["is_staff"], i["is_admin"], i["is_student"]) for c, i in courses.items()},
                         {str(CS169A): (True, False, False), "4567890": (False, False, True)})

    def test_finds_students_by_email(self):
        db.session.add(Offering(canvas_id=CS169A, key=str(CS169A), name="CS 169A"))
        db.session.commit()
        with self.app.test_request_context():
            load_offering(CS169A)
            self.assertEqual(canvas_service.get_student_from_email("jx@berkeley.edu", "dev_access_token"),
                             (JIMMY_XU, "Jimmy Xu"))
            # Staff aren't students.
            self.assertIsNone(canvas_service.get_student_from_email("long_yu@berkeley.edu", "dev_access_token"))

    def test_production_never_uses_the_fake_canvas(self):
        self.app.config["APP_ENV"] = "production"
        with self.app.test_request_context():
            self.assertFalse(canvas_service.is_mock_canvas())


class DevLoginTests(AppTestCase):
    config = {"MOCK_CANVAS": True}

    def dev_login(self, user_id, **kwargs):
        return self.post("/dev_login/", data={"user_id": user_id}, **kwargs)

    def test_login_goes_to_the_dev_login_page_and_back(self):
        response = self.get("/login/", query_string={"next": f"/offerings/{CS169A}/"})
        self.assertTrue(response.headers["Location"].endswith("/dev_login/"))
        page = self.get("/dev_login/").get_data(as_text=True)
        self.assertIn("Lavender Angela", page)
        self.assertEqual(page.count('name="user_id" value='), 5)

        response = self.dev_login(YU_LONG)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith(f"/offerings/{CS169A}/"))
        user = User.query.filter_by(canvas_id=YU_LONG).one()
        self.assertEqual((user.email, user.name), ("long_yu@berkeley.edu", "Yu Long"))
        self.assertEqual(set(user.canvas_courses), {str(CS169A), "4567890"})
        with self.client.session_transaction() as browser:
            self.assertEqual(browser["_user_id"], user.get_id())
            # a TA, so keeps the token to look up students
            self.assertEqual(browser["canvas_access_token"], "dev_access_token")

    def test_staff_can_set_up_a_course_and_add_students_from_the_fake_canvas(self):
        self.dev_login(OSKI)
        self.post("/offerings/new", data={"offerings": [str(CS169A)]})
        self.assertEqual(Offering.query.filter_by(canvas_id=CS169A).one().code, "COMPSCI 169A")
        section = lab(str(CS169A))
        db.session.add(section)
        db.session.commit()
        user = self.api("refresh_state", CS169A).get_json()["data"]["currentUser"]
        self.assertTrue(user["isAdmin"])
        body = self.api("add_students", CS169A, emails="jx@berkeley.edu", section_id=str(section.id)).get_json()
        self.assertTrue(body["success"], body)
        self.assertEqual(User.query.filter_by(email="jx@berkeley.edu").one().canvas_id, JIMMY_XU)

    def test_a_pasted_id_is_trimmed(self):
        # Copying an ID out of a spreadsheet brings whitespace with it.
        self.assertEqual(self.dev_login("  345678\n").status_code, 302)
        self.assertIsNotNone(User.query.filter_by(canvas_id="345678").one_or_none())

    def test_an_unknown_id_is_explained_rather_than_crashing(self):
        response = self.dev_login("999999", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("No seeded user has Canvas ID 999999", response.get_data(as_text=True))
        self.assertEqual(User.query.count(), 0)

    def test_a_missing_id_is_reported(self):
        response = self.dev_login("")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Enter a Canvas ID.", response.get_data(as_text=True))

    def test_page_is_hidden_when_canvas_is_real(self):
        self.app.config["MOCK_CANVAS"] = False
        for response in (self.get("/dev_login/"), self.dev_login(YU_LONG)):
            self.assertEqual(response.status_code, 302)
            self.assertNotIn("/dev_login", response.headers["Location"])
        self.assertEqual(User.query.count(), 0)

    def test_login_redirects_to_real_canvas_when_canvas_is_real(self):
        self.app.config["MOCK_CANVAS"] = False
        response = self.get("/login/")
        self.assertTrue(response.headers["Location"].startswith("https://canvas.test/login/oauth2/auth"))


if __name__ == "__main__":
    unittest.main()
