import time
import unittest
from unittest.mock import patch

from canvasapi.exceptions import InvalidAccessToken
from flask import Flask, g, session
from sqlalchemy.exc import NoResultFound

from offerings import create_offering_pages
from login import complete_login, create_login_client
from import_sheet import import_enrollment, import_sections, parse_time_string
from models import Attendance, AttendanceStatus, Offering, Section, Session, User, db, set_contains
from state import create_state_client

# Offering 101 was moved from the monorepo, so its rows use the old key "cs61a".
CS61A, DATA8, UNSET_UP = 101, 202, 303


def canvas_course(code, *, staff=False, admin=False, student=False):
    return {"name": f"{code} - LEC 001", "code": code, "start_at": "2026-08-19T07:00:00Z",
            "is_staff": staff, "is_admin": admin, "is_student": student}


def lab(course, location="Room"):
    return Section(course=course, name="Lab", location=location, description="",
                   capacity=30, can_self_enroll=True, start_time=0, end_time=3600)


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
        self.client = self.app.test_client()
        self.sign_in(self.staff)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def sign_in(self, user):
        with self.client.session_transaction() as browser:
            browser["_user_id"] = user.get_id()

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

    def enroll_known_in_data8(self):
        """Make "known" a student in DATA 8 too, enrolled in its lab."""
        known = db.session.get(User, self.known_id)
        known.canvas_courses = {**known.canvas_courses, str(DATA8): canvas_course("DATA 8", student=True)}
        known.set_role(str(DATA8), is_staff=False)
        known.sections.append(db.session.get(Section, self.data8_section_id))
        db.session.commit()
        return known

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
        with patch("state.canvas_service.get_student_from_email", return_value=("555", "New")) as lookup:
            self.assertTrue(self.add_students("new@test")["success"])
        lookup.assert_called_once_with("new@test", "access")
        db.session.remove()
        new = User.query.filter_by(email="new@test").one()
        # Recorded by Canvas id, so a later email change still finds them.
        self.assertEqual((new.canvas_id, new.student_offerings), ("555", {"cs61a"}))
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

    def log_in_as(self, canvas_id, email, courses=None, **profile):
        with self.app.test_request_context(), \
             patch("login.canvas_service.get_profile",
                   return_value={"primary_email": email, "short_name": "Name", **profile}), \
             patch("login.canvas_service.get_user_courses", return_value=courses or {}):
            complete_login({"user": {"id": canvas_id}, "access_token": "access"})

    def test_login_records_pronouns_as_shared_in_canvas(self):
        self.log_in_as(2, "known@test", pronouns="she/her")
        self.assertEqual(db.session.get(User, self.known_id).pronouns, "she/her")
        # Stopped sharing them: Canvas sends none, so they're cleared.
        self.log_in_as(2, "known@test")
        self.assertIsNone(db.session.get(User, self.known_id).pronouns)
        self.log_in_as(2, "known@test", pronouns="")
        self.assertIsNone(db.session.get(User, self.known_id).pronouns)

    def test_pronouns_show_only_where_the_name_does(self):
        known = db.session.get(User, self.known_id)
        section = db.session.get(Section, self.section_id)
        peer = User(email="peer@test", name="Peer", pronouns="they/them")
        unrelated = User(email="unrelated@test", name="Unrelated", pronouns="he/him")
        for person in (peer, unrelated):
            person.set_role("cs61a", is_staff=False)
        section.students.extend([known, peer])
        db.session.add_all([peer, unrelated])
        db.session.commit()
        self.sign_in(known)
        roster = self.api("refresh_state").get_json()["data"]["enrolledSections"][0]["students"]
        self.assertIn({"name": "Peer", "pronouns": "they/them"},
                      [{"name": p["name"], "pronouns": p["pronouns"]} for p in roster])
        # A classmate outside your sections is anonymized, pronouns included.
        with self.app.test_request_context():
            g.offering = Offering.query.filter_by(canvas_id=CS61A).one()
            g._login_user = db.session.get(User, self.known_id)
            hidden = db.session.get(User, unrelated.id).json
        self.assertEqual((hidden["name"], hidden["pronouns"]), ("Anon Student", None))

    def test_canvas_lookup_uses_the_display_name(self):
        import canvas_service

        class Enrollment:
            user = {"id": 555, "login_id": "new@test", "name": "Legal Name", "short_name": "Display Name"}

        client = patch("canvas_service._client").start()
        self.addCleanup(patch.stopall)
        client.return_value.get_course.return_value.get_enrollments.return_value = [Enrollment()]
        with self.app.test_request_context():
            g.offering = Offering.query.filter_by(canvas_id=CS61A).one()
            self.assertEqual(canvas_service.get_student_from_email("new@test", "token"), ("555", "Display Name"))
            self.assertIsNone(canvas_service.get_student_from_email("other@test", "token"))

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

    def test_student_refresh_uses_summaries_and_keeps_enrolled_roster(self):
        known = db.session.get(User, self.known_id)
        section = db.session.get(Section, self.section_id)
        peer = User(email="peer@test", name="Peer")
        unrelated = User(email="unrelated@test", name="Unrelated")
        for person in (peer, unrelated):
            person.set_role("cs61a", is_staff=False)
        other_section = Section(course="cs61a", name="Discussion", location="Other Room",
                                description="", capacity=25, can_self_enroll=True,
                                start_time=7200, end_time=10800)
        section.students.extend([known, peer])
        other_section.students.append(unrelated)
        db.session.add_all([peer, unrelated, other_section])
        db.session.commit()

        self.sign_in(self.known)
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
        with self.assertRaises(NoResultFound):  # a 500 outside tests
            self.api("claim_section", section_id=str(self.data8_section_id))
        self.assertIsNone(db.session.get(Section, self.data8_section_id).staff_id)
        # Not enrolled in DATA 8, so its pages and APIs are forbidden.
        self.assertEqual(self.api("refresh_state", DATA8).status_code, 403)
        self.assertEqual(self.get(f"/offerings/{DATA8}/").status_code, 403)

    def test_one_person_in_two_offerings_sees_each_separately(self):
        known = self.enroll_known_in_data8()
        known.sections.append(db.session.get(Section, self.section_id))
        db.session.commit()
        self.sign_in(known)
        for canvas_id, location in ((CS61A, "Room"), (DATA8, "Elsewhere")):
            state = self.api("refresh_state", canvas_id).get_json()["data"]
            self.assertEqual([s["location"] for s in state["enrolledSections"]], [location])

    def test_joining_a_lab_keeps_the_lab_in_another_offering(self):
        known = self.enroll_known_in_data8()
        self.sign_in(known)
        self.api("refresh_state")  # the app loads state (and the course config) first
        result = self.api("join_section", target_section_id=str(self.section_id)).get_json()
        self.assertTrue(result["success"], result)
        db.session.remove()
        sections = {s.id for s in db.session.get(User, self.known_id).sections}
        self.assertEqual(sections, {self.section_id, self.data8_section_id})

    def test_leaving_and_removal_only_affect_this_offering(self):
        known = self.enroll_known_in_data8()
        known.sections.append(db.session.get(Section, self.section_id))
        db.session.commit()
        self.sign_in(known)
        self.api("refresh_state")  # the app loads state (and the course config) first
        self.assertTrue(self.api("leave_all_sections").get_json()["success"])
        db.session.remove()
        self.assertEqual([s.id for s in db.session.get(User, self.known_id).sections],
                         [self.data8_section_id])

        # Admins removing a student also leave their other offerings alone.
        known = db.session.get(User, self.known_id)
        known.sections.append(db.session.get(Section, self.section_id))
        staff = db.session.get(User, self.staff_id)
        staff.canvas_courses = {str(CS61A): canvas_course("CS 61A", staff=True, admin=True)}
        db.session.commit()
        self.sign_in(staff)
        self.assertTrue(self.api("remove_students", students="known@test").get_json()["success"])
        db.session.remove()
        self.assertEqual([s.id for s in db.session.get(User, self.known_id).sections],
                         [self.data8_section_id])

    def test_attendance_history_is_per_offering(self):
        known = self.enroll_known_in_data8()
        data8_session = Session(course=str(DATA8), start_time=0, section_id=self.data8_section_id)
        db.session.add(data8_session)
        db.session.add(Attendance(course=str(DATA8), status=AttendanceStatus.present,
                                  session=data8_session, student=known))
        db.session.commit()
        self.sign_in(known)
        for canvas_id, expected in ((CS61A, 0), (DATA8, 1)):
            user = self.api("refresh_state", canvas_id).get_json()["data"]["currentUser"]
            self.assertEqual(len(user["attendanceHistory"]), expected)

    def test_reset_removes_sections_and_assignments_but_keeps_people(self):
        known = self.enroll_known_in_data8()
        section = db.session.get(Section, self.section_id)
        known.sections.append(section)
        section.staff = db.session.get(User, self.staff_id)
        session = Session(course="cs61a", start_time=0, section=section)
        db.session.add(Attendance(course="cs61a", status=AttendanceStatus.present,
                                  session=session, student=known))
        staff = db.session.get(User, self.staff_id)
        staff.canvas_courses = {str(CS61A): canvas_course("CS 61A", staff=True, admin=True)}
        db.session.commit()

        self.assertTrue(self.api("reset_sections").get_json()["success"])
        db.session.remove()
        self.assertIsNone(db.session.get(Section, self.section_id))
        self.assertEqual(Session.query.filter_by(course="cs61a").count(), 0)
        self.assertEqual(Attendance.query.filter_by(course="cs61a").count(), 0)
        known = db.session.get(User, self.known_id)
        # Still in the course, and untouched in DATA 8.
        self.assertEqual(known.student_offerings, {"cs61a", str(DATA8)})
        self.assertEqual([s.id for s in known.sections], [self.data8_section_id])
        self.assertIn("cs61a", db.session.get(User, self.staff_id).staff_offerings)

    def test_enrollment_import_keeps_same_type_sections_in_other_offerings(self):
        self.enroll_known_in_data8()  # in DATA 8's Lab
        cs61a_lab = db.session.get(Section, self.section_id)
        cs61a_lab.staff = db.session.get(User, self.staff_id)
        cs61a_lab.start_time = parse_time_string("M", "10:00a")
        db.session.commit()
        with self.app.test_request_context():
            g.offering = Offering.query.filter_by(canvas_id=CS61A).one()
            import_enrollment(iter([
                ["Student Email", "Student Name", "Staff Email", "Location", "Day", "Start", "Type"],
                ["known@test", "Known", "staff@test", "Room", "M", "10:00a", "Lab"],
            ]))
        db.session.remove()
        sections = {s.id for s in db.session.get(User, self.known_id).sections}
        self.assertEqual(sections, {self.section_id, self.data8_section_id})

    def test_sheet_times_are_integers(self):
        # Section times are Integer columns. Postgres rejects a float such as
        # 1629817200.0; SQLite silently stores it, so check before it's saved.
        self.assertEqual(parse_time_string("T", "08:00a"), 1629817200)  # Tue 2021-08-24 8am PDT
        with self.app.test_request_context(), patch.object(db.session, "commit"):
            g.offering = Offering.query.filter_by(canvas_id=CS61A).one()
            import_sections(iter([
                ["Email", "Name", "Capacity", "Location", "Day", "Start", "End", "Tags", "Can Self Enroll", "Type"],
                ["staff@test", "Staff", "35", "The Moon", "T", "08:00a", "09:30p", "", "TRUE", "Lab"],
            ]))
            [section] = [s for s in db.session.new if isinstance(s, Section)]
            self.assertEqual((section.start_time, section.end_time), (1629817200, 1629865800))
            self.assertIs(type(section.start_time), int)
            self.assertIs(type(section.end_time), int)

    def test_email_lookups_ignore_case(self):
        with patch("state.canvas_service.get_student_from_email") as lookup:
            self.assertTrue(self.add_students("KNOWN@Test")["success"])
        lookup.assert_not_called()  # found the existing person, no Canvas lookup
        self.assertEqual(User.query.count(), 2)

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

    def test_global_admins_count_as_members_everywhere(self):
        boss = User(email="boss@test", name="Boss", canvas_id="9", is_global_admin=True)
        db.session.add(boss)
        db.session.commit()
        result = self.api("get_userid", email="boss@test").get_json()
        self.assertEqual(result["data"], boss.id)

    def test_offering_keys_match_exactly(self):
        dash = User(email="dash@test", name="Dash")
        dash.set_role("cs61a-tutoring", is_staff=False)
        db.session.add(dash)
        db.session.commit()
        # "_" is a LIKE wildcard; it must not match "-".
        self.assertEqual(User.query.filter(set_contains(User.student_offerings, "cs61a_tutoring")).count(), 0)
        self.assertEqual(User.query.filter(set_contains(User.student_offerings, "cs61a-tutoring")).count(), 1)

    def test_sessions_can_only_start_for_this_offerings_sections(self):
        with self.assertRaises(NoResultFound):  # a 500 outside tests
            self.api("start_session", section_id=str(self.data8_section_id), start_time=0)
        self.assertEqual(Session.query.count(), 0)

    def test_course_that_is_not_set_up_is_not_found(self):
        self.assertEqual(self.api("refresh_state", UNSET_UP).status_code, 404)

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

    def test_staff_import_offerings_and_students_cannot(self):
        self.sign_in(self.known)
        self.post("/offerings/new", data={"offerings": [str(UNSET_UP)]})
        self.assertIsNone(Offering.query.filter_by(canvas_id=UNSET_UP).one_or_none())

        self.sign_in(self.staff)
        page = self.get("/offerings/new").get_data(as_text=True)
        self.assertIn(f'value="{UNSET_UP}"', page)
        self.assertIn("2026-08 | CS 70 | CS 70 - LEC 001", page)
        self.assertNotIn(f'value="{CS61A}"', page)  # already set up
        # Only courses the user is staff in can be imported.
        response = self.post("/offerings/new", data={"offerings": [str(UNSET_UP), str(DATA8), "999"]})
        self.assertTrue(response.headers["Location"].endswith("/offerings"))
        offering = Offering.query.filter_by(canvas_id=UNSET_UP).one()
        self.assertEqual((offering.key, offering.code, offering.start_month), (str(UNSET_UP), "CS 70", "2026-08"))
        self.assertIsNone(Offering.query.filter_by(canvas_id=999).one_or_none())
        self.assertTrue(self.api("refresh_state", UNSET_UP).get_json()["success"])

    def test_offerings_page_matches_seating(self):
        self.assertTrue(self.get("/").headers["Location"].endswith("/offerings"))
        page = self.get("/offerings").get_data(as_text=True)
        self.assertIn("Staff Course Offerings", page)
        self.assertIn(f'href="/offerings/{CS61A}/"', page)
        self.assertNotIn(f"/offerings/{DATA8}/", page)
        # The linked offering picked up its Canvas details.
        self.assertIn("CS 61A - LEC 001", page)
        self.assertEqual(Offering.query.filter_by(canvas_id=CS61A).one().code, "CS 61A")
        self.assertEqual(self.api("refresh_state").get_json()["data"]["course"], "CS 61A")

        self.sign_in(self.known)
        page = self.get("/offerings").get_data(as_text=True)
        student_part = page[page.index("Student Course Offerings"):page.index("Other Course Offerings")]
        self.assertIn(f'href="/offerings/{CS61A}/"', student_part)
        self.assertNotIn("/remove", page)  # only staff offerings can be removed

    def test_staff_remove_offerings_and_keep_their_data(self):
        page = self.get("/offerings").get_data(as_text=True)
        self.assertIn(f'action="/offerings/{CS61A}/remove"', page)

        # Students, and staff of other courses, cannot.
        self.sign_in(self.known)
        self.assertEqual(self.post(f"/offerings/{CS61A}/remove").status_code, 403)
        self.sign_in(self.staff)
        self.assertEqual(self.post(f"/offerings/{DATA8}/remove").status_code, 403)
        self.assertEqual(self.post("/offerings/999/remove").status_code, 404)
        self.assertEqual(self.get(f"/offerings/{CS61A}/remove").status_code, 405)

        # A course linked from the monorepo: removing it keeps its sections under
        # "cs61a", and the message says how to link them again.
        response = self.post(f"/offerings/{CS61A}/remove", follow_redirects=True)
        self.assertIn(f"flask link-offering {CS61A} cs61a", response.get_data(as_text=True))
        self.assertIsNone(Offering.query.filter_by(canvas_id=CS61A).one_or_none())
        self.assertNotIn(f"/offerings/{CS61A}/", self.get("/offerings").get_data(as_text=True))
        self.assertIsNotNone(db.session.get(Section, self.section_id))
        self.app.test_cli_runner().invoke(args=["link-offering", str(CS61A), "cs61a", "CS 61A"])
        sections = self.api("refresh_state").get_json()["data"]["sections"]
        self.assertEqual([s["id"] for s in sections], [str(self.section_id)])

        # A course imported here comes back with its sections by importing it again.
        self.post("/offerings/new", data={"offerings": [str(UNSET_UP)]})
        db.session.add(lab(str(UNSET_UP)))
        db.session.commit()
        response = self.post(f"/offerings/{UNSET_UP}/remove", follow_redirects=True)
        self.assertIn("import it again to restore them", response.get_data(as_text=True))
        self.post("/offerings/new", data={"offerings": [str(UNSET_UP)]})
        self.assertEqual(len(self.api("refresh_state", UNSET_UP).get_json()["data"]["sections"]), 1)

    def test_offerings_without_a_start_date_say_so(self):
        db.session.add(Offering(canvas_id=404, key="404", name="CS 10 - LEC 001", code="CS 10"))
        self.staff.canvas_courses = {**self.staff.canvas_courses,
                                     "404": {**canvas_course("CS 10", staff=True), "start_at": None}}
        db.session.commit()
        page = self.get("/offerings").get_data(as_text=True)
        self.assertIn('<small class="offering-term">No Date</small>', page)
        self.assertIn('<small class="offering-term">2026-08</small>', page)

    def test_offerings_pages_nav_and_import_button(self):
        page = self.get("/offerings").get_data(as_text=True)
        self.assertNotIn(">Home<", page)
        self.assertNotIn(">Offerings</a>", page)  # already on it
        page = self.get("/offerings/new").get_data(as_text=True)
        self.assertIn('href="/offerings">Offerings</a>', page)
        self.assertIn('value="Import"', page)

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


if __name__ == "__main__":
    unittest.main()
