"""Syncing an offering's students with its bCourses roster."""

import json

import sqlalchemy
from types import SimpleNamespace
from unittest.mock import patch

from canvasapi.exceptions import InvalidAccessToken
from flask import g

from server.models import Attendance, AttendanceStatus, Offering, Section, Session, User, db
from tests.unit.support import CS61A, DATA8, CourseTestCase, canvas_course


def entry(canvas_id, email, name="Name"):
    return {"canvas_id": canvas_id, "email": email, "name": name}


class SyncBcoursesTests(CourseTestCase):
    def setUp(self):
        super().setUp()
        self.make_staff_admin()
        self.authorize()

    def sync(self, roster, method="sync_bcourses"):
        with patch("server.state.canvas_service.get_roster", return_value=roster) as get_roster:
            body = self.api(method).get_json()
        db.session.remove()
        get_roster.assert_called_once_with("access")
        return body

    def students(self):
        return {user.email for user in User.query.all() if "cs61a" in user.student_offerings}

    def test_adds_roster_students_who_arent_here_yet(self):
        # "imported" came from a spreadsheet, so has no Canvas id until now.
        db.session.add(User(email="imported@test", name="Imported"))
        db.session.commit()
        roster = [entry("2", "known@test"), entry("3", "imported@test"), entry("4", "new@test", "New")]
        body = self.sync(roster)
        self.assertTrue(body["success"], body)
        self.assertEqual(body["data"]["custom"]["message"], "Added 2 students and removed 0.")
        self.assertEqual(self.students(), {"known@test", "imported@test", "new@test"})
        new = User.query.filter_by(email="new@test").one()
        self.assertEqual((new.canvas_id, new.name), ("4", "New"))
        self.assertEqual(User.query.filter_by(email="imported@test").one().canvas_id, "3")

    def test_removes_students_no_longer_on_the_roster(self):
        known = self.enroll_known_in_data8()
        known.sections.append(db.session.get(Section, self.section_id))
        session = Session(course="cs61a", start_time=0, section_id=self.section_id)
        db.session.add(Attendance(course="cs61a", status=AttendanceStatus.present, session=session, student=known))
        db.session.commit()

        body = self.sync([entry("9", "other@test")])
        self.assertTrue(body["success"], body)
        self.assertEqual(body["data"]["custom"]["message"], "Added 1 students and removed 1.")
        known = db.session.get(User, self.known_id)
        self.assertEqual(known.student_offerings, {str(DATA8)})
        # Out of this offering's sections only, and their attendance stays.
        self.assertEqual([s.id for s in known.sections], [self.data8_section_id])
        self.assertEqual(Attendance.query.filter_by(student_id=self.known_id).count(), 1)
        self.assertNotIn(str(CS61A), known.canvas_courses)
        self.assertIn(str(DATA8), known.canvas_courses)

        # Their attendance is still in the course's export, as is the student
        # who's still here, who has none.
        export = json.loads(self.api("export_attendance").get_json()["data"]["custom"]["attendances"])
        self.assertEqual(export, [{"type": "Lab", "attendances": {
            "known@test": [{"section_id": self.section_id, "start_time": 0, "status": "present"}],
            "other@test": [],
        }}])

        # The roles saved at their last sign-in don't bring them back.
        self.sign_in(known)
        self.assertEqual(self.api("refresh_state").status_code, 403)
        db.session.remove()
        self.assertNotIn("cs61a", db.session.get(User, self.known_id).student_offerings)

    def test_staff_are_left_alone(self):
        # On the roster as a student too, and absent from it: either way still staff.
        for roster in ([entry("1", "staff@test"), entry("2", "known@test")], [entry("2", "known@test")]):
            with self.subTest(roster=roster):
                self.assertTrue(self.sync(roster)["success"])
                staff = db.session.get(User, self.staff_id)
                self.assertEqual((staff.staff_offerings, staff.admin_offerings, staff.student_offerings),
                                 ({"cs61a"}, {"cs61a"}, set()))

    def test_preview_changes_nothing(self):
        body = self.sync([entry("4", "new@test")], method="preview_bcourses_sync")
        self.assertTrue(body["success"], body)
        self.assertEqual(body["data"], {"added": ["new@test"], "removed": ["known@test"], "skipped": [], "no_email": []})
        self.assertEqual(self.students(), {"known@test"})
        self.assertIsNone(User.query.filter_by(email="new@test").one_or_none())

    def test_someone_elses_email_is_skipped(self):
        # staff@test is Canvas user 1 here, so Canvas user 8 with that login isn't added.
        roster = [entry("2", "known@test"), entry("8", "staff@test")]
        body = self.sync(roster, method="preview_bcourses_sync")
        self.assertEqual(body["data"], {"added": [], "removed": [], "skipped": ["staff@test"], "no_email": []})
        body = self.sync(roster)
        self.assertTrue(body["success"], body)
        self.assertEqual(body["data"]["custom"]["message"],
                         "Added 0 students and removed 0. Didn't add 1 whose email belongs to a different "
                         "bCourses account in Sections: staff@test.")
        self.assertEqual(self.students(), {"known@test"})
        self.assertIsNone(User.query.filter_by(canvas_id="8").one_or_none())

    def test_without_an_email_only_known_students_are_matched(self):
        # Matched by Canvas id, they need no email; someone new can't be added without one.
        body = self.sync([entry("2", None), entry("4", None, "No Email")])
        self.assertTrue(body["success"], body)
        self.assertEqual(body["data"]["custom"]["message"],
                         "Added 0 students and removed 0. Didn't add 1 whose email bCourses didn't share: No Email.")
        self.assertEqual(self.students(), {"known@test"})

    def test_matching_takes_a_few_queries_however_many_students(self):
        # One or two queries per student made a large course take minutes.
        for i in range(30):
            user = User(email=f"s{i}@test", name="S", canvas_id=str(100 + i) if i % 2 else None)
            user.set_role("cs61a", is_staff=False)
            db.session.add(user)
        db.session.commit()
        roster = [entry(str(100 + i), f"S{i}@TEST") for i in range(30)] + [entry("2", "known@test")]
        statements = []
        listen = sqlalchemy.event.listens_for(db.engine, "before_cursor_execute")
        listen(lambda *args: statements.append(args[2]))
        body = self.sync(roster, method="preview_bcourses_sync")
        self.assertEqual(body["data"], {"added": [], "removed": [], "skipped": [], "no_email": []})
        self.assertLess(len(statements), 15, statements)

    def test_empty_roster_changes_nothing(self):
        body = self.sync([])
        self.assertFalse(body["success"])
        self.assertIn("no students", body["message"])
        self.assertEqual(self.students(), {"known@test"})

    def test_revoked_token_asks_to_sign_in_again(self):
        with patch("server.state.canvas_service.get_roster", side_effect=InvalidAccessToken("revoked")):
            body = self.api("sync_bcourses").get_json()
        self.assertFalse(body["success"])
        self.assertIn("sign in with Canvas again", body["message"])

    def test_expired_token_asks_to_sign_in_again(self):
        db.session.execute(db.text("UPDATE canvas_tokens SET expires_at = 0"))
        db.session.commit()
        with patch("server.state.canvas_service.get_roster") as get_roster:
            body = self.api("sync_bcourses").get_json()
        self.assertFalse(body["success"])
        self.assertIn("sign in with Canvas again", body["message"])
        get_roster.assert_not_called()

    def test_admins_only(self):
        staff = db.session.get(User, self.staff_id)
        staff.canvas_courses = {str(CS61A): canvas_course("CS 61A", staff=True)}
        staff.set_role("cs61a", is_staff=True)
        db.session.commit()
        with patch("server.state.canvas_service.get_roster") as get_roster:
            body = self.api("sync_bcourses").get_json()
        self.assertFalse(body["success"])
        get_roster.assert_not_called()


class GetRosterTests(CourseTestCase):
    def test_students_with_their_email_and_display_name(self):
        from server import canvas_service

        client = patch("server.canvas_service._client").start()
        self.addCleanup(patch.stopall)
        get_users = client.return_value.get_course.return_value.get_users
        # At Berkeley the login is a CalNet UID, not an email; and Canvas may not share an email.
        get_users.return_value = [
            SimpleNamespace(id=5, login_id="1717117", email="a@test", name="A", short_name="A (display)"),
            SimpleNamespace(id=6, login_id="1717118", name="B", short_name=""),
        ]
        with self.app.test_request_context():
            g.offering = Offering.query.filter_by(canvas_id=CS61A).one()
            self.assertEqual(canvas_service.get_roster("token"), [
                {"canvas_id": "5", "email": "a@test", "name": "A (display)"},
                {"canvas_id": "6", "email": None, "name": "B"},
            ])
        get_users.assert_called_once_with(enrollment_type=["student"], enrollment_state=["active", "invited"],
                                          include=["email"], per_page=100)
