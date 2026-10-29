"""Shared setup for the unit tests: the app built as in production, by
create_app, with a test config, and the course data most tests start from."""

import time
import unittest
from unittest.mock import patch

from flask import g

from application import create_app
from import_sheet import import_sections
from login import complete_login
from models import Offering, Section, User, db

TEST_CONFIG = {
    "SECRET_KEY": "test",
    "TESTING": True,
    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    "CANVAS_SERVER_URL": "https://canvas.test/",
    "CANVAS_CLIENT_ID": "id",
    "CANVAS_CLIENT_SECRET": "secret",
}

# Offering 101 was moved from the monorepo, so its rows use the old key "cs61a".
CS61A, DATA8, UNSET_UP = 101, 202, 303


def canvas_course(code, *, staff=False, admin=False, student=False):
    return {"name": f"{code} - LEC 001", "code": code, "start_at": "2026-08-19T07:00:00Z",
            "is_staff": staff, "is_admin": admin, "is_student": student}


def lab(course, location="Room"):
    return Section(course=course, name="Lab", location=location, description="",
                   capacity=30, can_self_enroll=True, start_time=0, end_time=3600)


class AppTestCase(unittest.TestCase):
    """The app with an empty database, and a test client."""

    config = {}

    def setUp(self):
        self.app = create_app({**TEST_CONFIG, **self.config})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        # Close the test app's connections, rather than leaving them to the
        # garbage collector (a ResourceWarning).
        db.engine.dispose()
        self.context.pop()

    def sign_in(self, user):
        with self.client.session_transaction() as browser:
            browser["_user_id"] = user.get_id()

    def get(self, path, **kwargs):
        self.clear_request_globals()
        return self.client.get(path, **kwargs)

    def post(self, path, **kwargs):
        self.clear_request_globals()
        return self.client.post(path, **kwargs)

    @staticmethod
    def clear_request_globals():
        # setUp keeps an app context open for database access, and Flask reuses
        # it for test requests, so per-request values on g would otherwise leak
        # between requests. In production each request gets a fresh context.
        for key in ("offering", "_login_user"):
            g.pop(key, None)

    def api(self, method, canvas_course_id=CS61A, **args):
        return self.post(f"/offerings/{canvas_course_id}/api/{method}", json=args)


class CourseTestCase(AppTestCase):
    """Two offerings (CS 61A, moved from the monorepo, and DATA 8), a staff
    member and a student in CS 61A, and a lab in each, signed in as staff."""

    def setUp(self):
        super().setUp()
        db.session.add_all([
            # Linked from the monorepo: no Canvas details until a member signs in.
            Offering(canvas_id=CS61A, key="cs61a", name="CS 61A"),
            Offering(canvas_id=DATA8, key=str(DATA8), name="DATA 8 - LEC 001", code="DATA 8",
                     start_at="2026-08-19T07:00:00Z"),
        ])
        self.staff = User(email="staff@test", name="Staff", canvas_id="1", canvas_courses={
            str(CS61A): canvas_course("CS 61A", staff=True),
            str(UNSET_UP): canvas_course("CS 70", staff=True, admin=True),
        })
        self.staff.set_role("cs61a", is_staff=True)
        self.known = User(email="known@test", name="Known", canvas_id="2", canvas_courses={
            str(CS61A): canvas_course("CS 61A", student=True),
            str(UNSET_UP): canvas_course("CS 70", student=True),
        })
        self.known.set_role("cs61a", is_staff=False)
        section = lab("cs61a")
        data8_section = lab(str(DATA8), location="Elsewhere")
        db.session.add_all([self.staff, self.known, section, data8_section])
        db.session.commit()
        self.section_id = section.id
        self.data8_section_id = data8_section.id
        self.staff_id, self.known_id = self.staff.id, self.known.id
        self.sign_in(self.staff)

    def add_students(self, emails):
        response = self.api("add_students", emails=emails, section_id=str(self.section_id))
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def authorize(self, expires_in=3600):
        with self.client.session_transaction() as browser:
            browser["canvas_access_token"] = "access"
            browser["canvas_token_expires_at"] = time.time() + expires_in

    def enroll_known_in_data8(self):
        """Make "known" a student in DATA 8 too, enrolled in its lab."""
        known = db.session.get(User, self.known_id)
        known.canvas_courses = {**known.canvas_courses, str(DATA8): canvas_course("DATA 8", student=True)}
        known.set_role(str(DATA8), is_staff=False)
        known.sections.append(db.session.get(Section, self.data8_section_id))
        db.session.commit()
        return known

    def log_in_as(self, canvas_id, email, courses=None, **profile):
        with self.app.test_request_context(), \
             patch("login.canvas_service.get_profile",
                   return_value={"primary_email": email, "short_name": "Name", **profile}), \
             patch("login.canvas_service.get_user_courses", return_value=courses or {}):
            complete_login({"user": {"id": canvas_id}, "access_token": "access"})

    SECTIONS_HEADER = ["Email", "Name", "Capacity", "Location", "Day", "Start", "End", "Tags",
                       "Can Self Enroll", "Type"]

    def import_cs61a_sections(self, *rows):
        with self.app.test_request_context():
            g.offering = Offering.query.filter_by(canvas_id=CS61A).one()
            result = import_sections(iter([self.SECTIONS_HEADER, *rows]))
        db.session.remove()
        return result

    def make_staff_admin(self):
        staff = db.session.get(User, self.staff_id)
        staff.canvas_courses = {str(CS61A): canvas_course("CS 61A", staff=True, admin=True)}
        staff.set_role("cs61a", is_staff=True, is_admin=True)
        db.session.commit()
