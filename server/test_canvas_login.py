import time
import unittest
from unittest.mock import patch

from canvasapi.exceptions import InvalidAccessToken
from flask import Flask, g, session
from sqlalchemy.exc import NoResultFound

from offerings import create_offering_pages
from login import complete_login, create_login_client
from models import Account, Offering, Section, User, db
from state import create_state_client

# Course 101 was moved from the monorepo, so its rows use the old key "cs61a".
CS61A, DATA8, UNSET_UP = 101, 202, 303


def canvas_course(code, *, staff=False, admin=False, student=False):
    return {"name": f"{code} - LEC 001", "code": code, "start_at": "2026-08-19T07:00:00Z",
            "is_staff": staff, "is_admin": admin, "is_student": student}


class CanvasLoginTests(unittest.TestCase):
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
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        db.session.add_all([
            # Linked from the monorepo: no Canvas details until a member signs in.
            Offering(canvas_id=CS61A, key="cs61a", name="CS 61A"),
            Offering(canvas_id=DATA8, key=str(DATA8), name="DATA 8 - LEC 001", code="DATA 8",
                   start_at="2026-08-19T07:00:00Z"),
        ])
        self.staff_account = Account(canvas_id="1", email="staff@test", name="Staff", canvas_courses={
            str(CS61A): canvas_course("CS 61A", staff=True),
            str(UNSET_UP): canvas_course("CS 70", staff=True, admin=True),
        })
        self.known_account = Account(canvas_id="2", email="known@test", name="Known", canvas_courses={
            str(CS61A): canvas_course("CS 61A", student=True),
            str(UNSET_UP): canvas_course("CS 70", student=True),
        })
        staff = User(email="staff@test", name="Staff", is_staff=True, is_admin=False, course="cs61a")
        known = User(email="known@test", name="Known", is_staff=False, is_admin=False, course="cs61a")
        section = Section(course="cs61a", name="Lab", location="Room", description="",
                          capacity=30, can_self_enroll=True, start_time=0, end_time=3600)
        data8_section = Section(course=str(DATA8), name="Lab", location="Elsewhere",
                                description="", capacity=30, can_self_enroll=True,
                                start_time=0, end_time=3600)
        db.session.add_all([self.staff_account, self.known_account, staff, known, section, data8_section])
        db.session.commit()
        self.staff_id = staff.id
        self.known_id = known.id
        self.section_id = section.id
        self.client = self.app.test_client()
        self.sign_in(self.staff_account)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def sign_in(self, account):
        with self.client.session_transaction() as browser:
            browser["_user_id"] = account.get_id()

    def get(self, path):
        self.clear_request_globals()
        return self.client.get(path)

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

    def add_students(self, emails):
        response = self.api("add_students", emails=emails, section_id=str(self.section_id))
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def authorize(self, expires_in=3600):
        with self.client.session_transaction() as browser:
            browser["canvas_access_token"] = "access"
            browser["canvas_token_expires_at"] = time.time() + expires_in

    def test_existing_students_need_no_canvas_token(self):
        with patch("state.canvas_service.get_student_from_email") as lookup:
            self.assertTrue(self.add_students("known@test")["success"])
        lookup.assert_not_called()

    def test_expired_or_missing_token_requests_reauthentication_without_partial_batch(self):
        for expires_in in (None, -1):
            with self.subTest(expires_in=expires_in):
                if expires_in is not None:
                    self.authorize(expires_in)
                with patch("state.canvas_service.get_student_from_email") as lookup:
                    result = self.add_students("known@test,new@test")
                self.assertFalse(result["success"])
                self.assertIn("sign in", result["message"])
                lookup.assert_not_called()
                db.session.remove()
                self.assertEqual(db.session.get(Section, self.section_id).students, [])

    def test_fresh_token_is_passed_to_canvas(self):
        self.authorize()
        with patch("state.canvas_service.get_student_from_email", return_value="New") as lookup:
            self.assertTrue(self.add_students("new@test")["success"])
        lookup.assert_called_once_with("new@test", "access")
        db.session.remove()
        new = User.query.filter_by(email="new@test").one()
        self.assertEqual(new.course, "cs61a")
        self.assertEqual([s.id for s in new.sections], [self.section_id])

    def test_revoked_token_requests_reauthentication(self):
        self.authorize()
        with patch("state.canvas_service.get_student_from_email", side_effect=InvalidAccessToken("revoked")):
            result = self.add_students("new@test")
        self.assertFalse(result["success"])
        self.assertIn("sign in", result["message"])

    def test_login_retains_only_staff_access_token_and_logout_clears_it(self):
        for is_staff in (True, False):
            with self.subTest(is_staff=is_staff), self.app.test_request_context():
                session["canvas_access_token"] = "previous"
                session["canvas_token_expires_at"] = 123
                courses = {str(CS61A): canvas_course("CS 61A", staff=is_staff, student=not is_staff)}
                with patch("login.canvas_service.get_profile",
                           return_value={"primary_email": "staff@test", "short_name": "Staff"}), \
                     patch("login.canvas_service.get_user_courses", return_value=courses):
                    complete_login({
                        "user": {"id": 1}, "access_token": "access",
                        "refresh_token": "must-not-be-stored", "expires_in": 3600,
                    })
                self.assertEqual(session.get("canvas_access_token"), "access" if is_staff else None)
                self.assertNotIn("refresh_token", session)
                self.assertTrue(session.permanent)
                self.assertEqual(session["_user_id"], self.staff_account.get_id())
                self.assertEqual(db.session.get(Account, self.staff_account.id).canvas_courses, courses)
        self.authorize()
        self.get("/logout/")
        with self.client.session_transaction() as browser:
            self.assertNotIn("canvas_access_token", browser)
            self.assertNotIn("canvas_token_expires_at", browser)

    def test_admin_override_course_makes_global_admin(self):
        self.app.config["ADMIN_OVERRIDE_CANVAS_COURSE_ID"] = 999
        with self.app.test_request_context(), \
             patch("login.canvas_service.get_profile", return_value={"primary_email": "boss@test"}), \
             patch("login.canvas_service.get_user_courses",
                   return_value={"999": canvas_course("Override", student=True)}):
            complete_login({"user": {"id": 9}, "access_token": "access"})
            self.assertIsNotNone(session.get("canvas_access_token"))
        boss = Account.query.filter_by(canvas_id="9").one()
        self.assertTrue(boss.is_global_admin)
        self.sign_in(boss)
        user = self.api("refresh_state", DATA8).get_json()["data"]["currentUser"]
        self.assertTrue(user["isStaff"])
        self.assertTrue(user["isAdmin"])

    def test_student_refresh_uses_summaries_and_keeps_enrolled_roster(self):
        known = db.session.get(User, self.known_id)
        section = db.session.get(Section, self.section_id)
        peer = User(email="peer@test", name="Peer", is_staff=False, is_admin=False, course="cs61a")
        unrelated = User(email="unrelated@test", name="Unrelated", is_staff=False,
                         is_admin=False, course="cs61a")
        other_section = Section(course="cs61a", name="Discussion", location="Other Room",
                                description="", capacity=25, can_self_enroll=True,
                                start_time=7200, end_time=10800)
        section.students.extend([known, peer])
        other_section.students.append(unrelated)
        db.session.add_all([peer, unrelated, other_section])
        db.session.commit()

        self.sign_in(self.known_account)
        response = self.api("refresh_state")

        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertTrue(result["success"])
        state = result["data"]
        self.assertEqual(state["course"], "CS 61A")
        self.assertEqual(state["currentUser"]["id"], self.known_id)
        summaries = {item["id"]: item for item in state["sections"]}

        enrolled_summary = summaries[str(self.section_id)]
        other_summary = summaries[str(other_section.id)]
        self.assertEqual(enrolled_summary["enrollmentCount"], 2)
        self.assertEqual(len(enrolled_summary["students"]), 2)
        self.assertEqual(enrolled_summary["students"], [None, None])
        self.assertEqual(other_summary["enrollmentCount"], 1)
        self.assertEqual(other_summary["students"], [None])

        self.assertEqual(len(state["enrolledSections"]), 1)
        roster = state["enrolledSections"][0]["students"]
        self.assertEqual(
            {student["email"] for student in roster},
            {"known@test", "peer@test"},
        )
        self.assertNotIn("unrelated@test", response.get_data(as_text=True))

    def test_courses_are_isolated(self):
        state = self.api("refresh_state").get_json()["data"]
        self.assertEqual([s["location"] for s in state["sections"]], ["Room"])
        # Sections from another course can't be reached through this one.
        data8_section = Section.query.filter_by(course=str(DATA8)).one()
        with self.assertRaises(NoResultFound):  # a 500 outside tests
            self.api("claim_section", section_id=str(data8_section.id))
        self.assertIsNone(db.session.get(Section, data8_section.id).staff_id)
        # Not enrolled in DATA 8, so its pages and APIs are forbidden.
        self.assertEqual(self.api("refresh_state", DATA8).status_code, 403)
        self.assertEqual(self.get(f"/offerings/{DATA8}/").status_code, 403)

    def test_course_that_is_not_set_up_is_not_found(self):
        self.assertEqual(self.api("refresh_state", UNSET_UP).status_code, 404)

    def test_first_visit_creates_course_user_and_roles_follow_canvas(self):
        self.staff_account.canvas_courses = {
            **self.staff_account.canvas_courses,
            str(DATA8): canvas_course("DATA 8", staff=True, admin=True),
        }
        db.session.commit()
        user = self.api("refresh_state", DATA8).get_json()["data"]["currentUser"]
        self.assertTrue(user["isAdmin"])
        self.assertEqual(User.query.filter_by(email="staff@test", course=str(DATA8)).count(), 1)

        # Dropped from staff in Canvas: the next sign-in updates the account,
        # and the course user follows.
        self.staff_account.canvas_courses = {str(CS61A): canvas_course("CS 61A", student=True)}
        db.session.commit()
        user = self.api("refresh_state").get_json()["data"]["currentUser"]
        self.assertEqual(user["id"], self.staff_id)
        self.assertFalse(user["isStaff"])

    def test_staff_import_offerings_and_students_cannot(self):
        self.sign_in(self.known_account)
        self.post("/offerings/new", data={"offerings": [str(UNSET_UP)]})
        self.assertIsNone(Offering.query.filter_by(canvas_id=UNSET_UP).one_or_none())

        self.sign_in(self.staff_account)
        page = self.get("/offerings/new").get_data(as_text=True)
        self.assertIn(f'value="{UNSET_UP}"', page)
        self.assertIn("2026-08 | CS 70 | CS 70 - LEC 001", page)
        self.assertNotIn(f'value="{CS61A}"', page)  # already set up
        # Only courses the user is staff in can be imported.
        response = self.post("/offerings/new", data={"offerings": [str(UNSET_UP), str(DATA8), "999"]})
        self.assertTrue(response.headers["Location"].endswith("/offerings"))
        course = Offering.query.filter_by(canvas_id=UNSET_UP).one()
        self.assertEqual((course.key, course.code, course.start_month), (str(UNSET_UP), "CS 70", "2026-08"))
        self.assertIsNone(Offering.query.filter_by(canvas_id=999).one_or_none())
        self.assertTrue(self.api("refresh_state", UNSET_UP).get_json()["success"])

    def test_offerings_page_matches_seating(self):
        self.assertTrue(self.get("/").headers["Location"].endswith("/offerings"))
        page = self.get("/offerings").get_data(as_text=True)
        self.assertIn("Staff Course Offerings", page)
        self.assertIn(f'href="/offerings/{CS61A}/"', page)
        self.assertNotIn(f"/offerings/{DATA8}/", page)
        # The linked course picked up its Canvas details.
        self.assertIn("CS 61A - LEC 001", page)
        self.assertEqual(Offering.query.filter_by(canvas_id=CS61A).one().code, "CS 61A")
        self.assertEqual(self.api("refresh_state").get_json()["data"]["course"], "CS 61A")

        self.sign_in(self.known_account)
        page = self.get("/offerings").get_data(as_text=True)
        student_part = page[page.index("Student Course Offerings"):page.index("Other Course Offerings")]
        self.assertIn(f'href="/offerings/{CS61A}/"', student_part)

    def test_logged_out_pages_go_to_login_and_apis_return_401(self):
        with self.client.session_transaction() as browser:
            browser.clear()
        self.assertIn("Login", self.get("/").get_data(as_text=True))
        self.assertIn("/login/", self.get("/offerings").headers["Location"])
        self.assertEqual(self.api("join_section", target_section_id=str(self.section_id)).status_code, 401)

    def test_session_from_before_accounts_is_ignored(self):
        # Sessions from the single-course app hold a per-course User id.
        with self.client.session_transaction() as browser:
            browser["_user_id"] = str(self.staff_account.id)
        state = self.api("refresh_state").get_json()["data"]
        self.assertIsNone(state["currentUser"])


if __name__ == "__main__":
    unittest.main()
