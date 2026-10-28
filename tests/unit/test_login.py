"""Signing in with bCourses: matching people, emails, roles and pronouns."""

from unittest.mock import patch

from flask import session

from login import complete_login
from models import Attendance, AttendanceStatus, Section, Session, User, db
from tests.unit.support import CS61A, CourseTestCase, DATA8, canvas_course, lab


class LoginTests(CourseTestCase):
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
                self.assertEqual(session["_user_id"], self.staff.get_id())
                self.assertEqual(db.session.get(User, self.staff_id).canvas_courses, courses)
        self.authorize()
        self.get("/logout/")
        with self.client.session_transaction() as browser:
            self.assertNotIn("canvas_access_token", browser)
            self.assertNotIn("canvas_token_expires_at", browser)

    def test_first_login_claims_the_imported_person_with_that_email(self):
        imported = User(email="tutor@test", name="Imported Name")
        imported.set_role("cs61a", is_staff=True)
        db.session.add(imported)
        db.session.commit()
        with self.app.test_request_context(), \
             patch("login.canvas_service.get_profile",
                   return_value={"primary_email": "tutor@test", "short_name": "Canvas Name"}), \
             patch("login.canvas_service.get_user_courses",
                   return_value={str(CS61A): canvas_course("CS 61A", staff=True)}):
            complete_login({"user": {"id": 77}, "access_token": "access"})
        self.assertEqual(User.query.filter_by(email="tutor@test").count(), 1)
        tutor = db.session.get(User, imported.id)
        self.assertEqual((tutor.canvas_id, tutor.name), ("77", "Canvas Name"))
        self.assertEqual(tutor.staff_offerings, {"cs61a"})

    def test_login_records_pronouns_as_shared_in_canvas(self):
        self.log_in_as(2, "known@test", pronouns="she/her")
        self.assertEqual(db.session.get(User, self.known_id).pronouns, "she/her")
        # Stopped sharing them: Canvas sends none, so they're cleared.
        self.log_in_as(2, "known@test")
        self.assertIsNone(db.session.get(User, self.known_id).pronouns)
        self.log_in_as(2, "known@test", pronouns="")
        self.assertIsNone(db.session.get(User, self.known_id).pronouns)

    def test_login_never_claims_someone_else_by_email(self):
        # Canvas user 99 has the email of "staff" (Canvas user 1).
        with self.assertRaises(Exception) as raised:
            self.log_in_as(99, "staff@test")
        self.assertEqual(getattr(raised.exception, "code", None), 403)
        db.session.rollback()
        staff = db.session.get(User, self.staff_id)
        self.assertEqual((staff.canvas_id, staff.email), ("1", "staff@test"))

    def test_changed_email_follows_the_canvas_id(self):
        self.log_in_as(2, "known.new@test")
        known = db.session.get(User, self.known_id)
        self.assertEqual(known.email, "known.new@test")
        self.assertEqual(User.query.count(), 2)

    def test_changed_email_merges_the_imported_record_with_that_email(self):
        imported = User(email="known.new@test", name="Imported")
        imported.set_role(str(DATA8), is_staff=True)
        imported.sections.append(db.session.get(Section, self.data8_section_id))
        db.session.add(imported)
        db.session.commit()
        imported_id = imported.id
        db.session.get(Section, self.data8_section_id).staff_id = imported_id
        data8_session = Session(course=str(DATA8), start_time=0, section_id=self.data8_section_id)
        db.session.add(Attendance(course=str(DATA8), status=AttendanceStatus.present,
                                  session=data8_session, student=imported))
        db.session.commit()

        self.log_in_as(2, "known.new@test")
        db.session.remove()
        self.assertIsNone(db.session.get(User, imported_id))
        known = db.session.get(User, self.known_id)
        self.assertEqual(known.email, "known.new@test")
        self.assertEqual(known.staff_offerings, {str(DATA8)})
        self.assertEqual(known.student_offerings, {"cs61a"})
        self.assertEqual([s.id for s in known.sections], [self.data8_section_id])
        self.assertEqual(db.session.get(Section, self.data8_section_id).staff_id, self.known_id)
        self.assertEqual([a.student_id for a in Attendance.query.all()], [self.known_id])

    def test_changed_email_owned_by_another_account_keeps_the_old_one(self):
        self.log_in_as(2, "staff@test")
        self.assertEqual(db.session.get(User, self.known_id).email, "known@test")
        self.assertEqual(db.session.get(User, self.staff_id).email, "staff@test")

    def test_merging_keeps_one_section_per_type_in_an_offering(self):
        known = db.session.get(User, self.known_id)
        known.sections.append(db.session.get(Section, self.section_id))
        other_lab = lab("cs61a", location="Other Room")
        imported = User(email="known.new@test", name="Imported")
        imported.set_role("cs61a", is_staff=False)
        imported.sections.append(other_lab)
        db.session.add_all([other_lab, imported])
        db.session.commit()
        self.log_in_as(2, "known.new@test")
        db.session.remove()
        self.assertEqual([s.id for s in db.session.get(User, self.known_id).sections], [self.section_id])

    def test_admin_override_course_makes_global_admin(self):
        self.app.config["ADMIN_OVERRIDE_CANVAS_COURSE_ID"] = 999
        with self.app.test_request_context(), \
             patch("login.canvas_service.get_profile", return_value={"primary_email": "boss@test"}), \
             patch("login.canvas_service.get_user_courses",
                   return_value={"999": canvas_course("Override", student=True)}):
            complete_login({"user": {"id": 9}, "access_token": "access"})
            self.assertIsNotNone(session.get("canvas_access_token"))
        boss = User.query.filter_by(canvas_id="9").one()
        self.assertTrue(boss.is_global_admin)
        self.sign_in(boss)
        user = self.api("refresh_state", DATA8).get_json()["data"]["currentUser"]
        self.assertTrue(user["isStaff"])
        self.assertTrue(user["isAdmin"])

    def test_roles_follow_canvas(self):
        staff = db.session.get(User, self.staff_id)
        staff.canvas_courses = {
            **staff.canvas_courses,
            str(DATA8): canvas_course("DATA 8", staff=True, admin=True),
        }
        db.session.commit()
        user = self.api("refresh_state", DATA8).get_json()["data"]["currentUser"]
        self.assertTrue(user["isAdmin"])
        self.assertIn(str(DATA8), db.session.get(User, self.staff_id).admin_offerings)

        # Dropped from staff in Canvas: the next login updates canvas_courses,
        # and the offering role follows.
        staff = db.session.get(User, self.staff_id)
        staff.canvas_courses = {str(CS61A): canvas_course("CS 61A", student=True)}
        db.session.commit()
        user = self.api("refresh_state").get_json()["data"]["currentUser"]
        self.assertEqual(user["id"], self.staff_id)
        self.assertFalse(user["isStaff"])

    def test_logged_out_pages_go_to_login_and_apis_return_401(self):
        with self.client.session_transaction() as browser:
            browser.clear()
        self.assertIn("Login", self.get("/").get_data(as_text=True))
        self.assertIn("/login/", self.get("/offerings").headers["Location"])
        self.assertEqual(self.api("join_section", target_section_id=str(self.section_id)).status_code, 401)

    def test_sessions_from_before_this_change_are_ignored(self):
        # Older cookies hold a per-course row id or an "account-" id.
        for old_id in (str(self.staff_id), f"account-{self.staff_id}"):
            with self.subTest(old_id=old_id):
                with self.client.session_transaction() as browser:
                    browser["_user_id"] = old_id
                state = self.api("refresh_state").get_json()["data"]
                self.assertIsNone(state["currentUser"])
