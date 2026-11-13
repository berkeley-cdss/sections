"""Syncing an offering's students with its bCourses roster."""

import json

import sqlalchemy
from unittest.mock import patch

from canvasapi.exceptions import InvalidAccessToken

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
        self.assertEqual(body["data"], {"added": ["new@test"], "removed": ["known@test"], "updated": [],
                                        "conflicts": [], "skipped": [], "no_email": []})
        self.assertEqual(self.students(), {"known@test"})
        self.assertIsNone(User.query.filter_by(email="new@test").one_or_none())

    def test_someone_elses_email_is_skipped(self):
        # staff@test is Canvas user 1 here, so Canvas user 8 with that login isn't added.
        roster = [entry("2", "known@test"), entry("8", "staff@test")]
        body = self.sync(roster, method="preview_bcourses_sync")
        self.assertEqual(body["data"], {"added": [], "removed": [], "updated": [], "conflicts": [],
                                        "skipped": ["staff@test"], "no_email": []})
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
        self.assertEqual(body["data"], {"added": [], "removed": [], "updated": [], "conflicts": [],
                                        "skipped": [], "no_email": []})
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


class SyncEmailTests(CourseTestCase):
    """Syncing also updates the emails of people whose bCourses email changed."""

    sync = SyncBcoursesTests.sync

    def setUp(self):
        super().setUp()
        self.make_staff_admin()
        self.authorize()

    def test_updates_a_changed_email(self):
        body = self.sync([entry("2", "Changed@test")], method="preview_bcourses_sync")
        self.assertEqual(body["data"]["updated"], ["known@test → Changed@test"])
        self.assertEqual(db.session.get(User, self.known_id).email, "known@test")

        body = self.sync([entry("2", "Changed@test")])
        self.assertTrue(body["success"], body)
        self.assertEqual(body["data"]["custom"]["message"],
                         "Added 0 students and removed 0. Updated 1 emails: known@test → Changed@test.")
        self.assertEqual(db.session.get(User, self.known_id).email, "Changed@test")

    def test_a_change_of_case_alone_isnt_an_update(self):
        body = self.sync([entry("2", "KNOWN@test")], method="preview_bcourses_sync")
        self.assertEqual(body["data"]["updated"], [])

    def test_without_an_email_the_email_stays(self):
        self.sync([entry("2", None)])
        self.assertEqual(db.session.get(User, self.known_id).email, "known@test")

    def test_someone_imported_under_the_new_email_is_merged(self):
        # Staff imported the student's new email before the student's next sign-in.
        imported = User(email="new@test", name="Imported")
        imported.set_role("cs61a", is_staff=False)
        imported.sections.append(db.session.get(Section, self.section_id))
        db.session.add(imported)
        db.session.commit()
        imported_id = imported.id

        body = self.sync([entry("2", "new@test")])
        self.assertTrue(body["success"], body)
        self.assertIn("Updated 1 emails: known@test → new@test.", body["data"]["custom"]["message"])
        self.assertIsNone(db.session.get(User, imported_id))
        known = db.session.get(User, self.known_id)
        self.assertEqual(known.email, "new@test")
        self.assertEqual([s.id for s in known.sections], [self.section_id])

    def test_an_email_belonging_to_another_bcourses_account_stays(self):
        # staff@test is Canvas user 1, so "known" (Canvas user 2) keeps their email.
        conflict = ("bCourses user 2 (known@test) has staff@test on bCourses, "
                    "but in Sections it belongs to bCourses user 1")
        body = self.sync([entry("2", "staff@test")], method="preview_bcourses_sync")
        self.assertEqual((body["data"]["updated"], body["data"]["conflicts"]), ([], [conflict]))
        with self.assertLogs(self.app.logger, "WARNING") as logs:
            body = self.sync([entry("2", "staff@test")])
        self.assertTrue(body["success"], body)
        self.assertEqual(body["data"]["custom"]["message"],
                         "Added 0 students and removed 0. Didn't update 1 emails that belong to a different "
                         f"bCourses account in Sections: {conflict}.")
        self.assertEqual([record.getMessage() for record in logs.records],
                         [f"bCourses sync in cs61a didn't update an email: {conflict}"])
        self.assertEqual(db.session.get(User, self.known_id).email, "known@test")
        self.assertEqual(db.session.get(User, self.staff_id).email, "staff@test")


class MergeStudentsTests(CourseTestCase):
    """Admins merging a student imported under an old email into the same
    student under their new one."""

    def setUp(self):
        super().setUp()
        self.make_staff_admin()
        # Imported as old@test, with a section and attendance, then signed in
        # (as "known", Canvas user 2) after changing their email.
        old = User(email="old@test", name="Old")
        old.set_role("cs61a", is_staff=False)
        old.sections.append(db.session.get(Section, self.section_id))
        session = Session(course="cs61a", start_time=0, section_id=self.section_id)
        db.session.add_all([old, Attendance(course="cs61a", status=AttendanceStatus.present,
                                            session=session, student=old)])
        db.session.commit()
        self.old_id = old.id

    def merge(self, old_email="old@test", new_email="known@test"):
        body = self.api("merge_students", old_email=old_email, new_email=new_email).get_json()
        db.session.remove()
        return body

    def test_moves_sections_and_attendance(self):
        body = self.merge(" OLD@test ")
        self.assertTrue(body["success"], body)
        self.assertEqual(body["data"]["custom"]["message"], "Merged OLD@test into known@test.")
        self.assertIsNone(db.session.get(User, self.old_id))
        known = db.session.get(User, self.known_id)
        self.assertEqual([s.id for s in known.sections], [self.section_id])
        self.assertEqual(Attendance.query.filter_by(student_id=self.known_id).count(), 1)
        self.assertEqual(known.canvas_id, "2")

    def test_works_after_a_sync_removed_the_old_email(self):
        # bCourses only has the new email, so a sync drops old@test from the course.
        old = db.session.get(User, self.old_id)
        old.student_offerings = set()
        old.sections = []
        db.session.commit()
        self.assertTrue(self.merge()["success"])
        self.assertEqual(Attendance.query.filter_by(student_id=self.known_id).count(), 1)

    def test_refuses_an_email_someone_signed_in_with(self):
        old = db.session.get(User, self.old_id)
        old.canvas_id = "9"
        db.session.commit()
        body = self.merge()
        self.assertFalse(body["success"])
        self.assertIn("signed in", body["message"])
        self.assertIsNotNone(db.session.get(User, self.old_id))

    def test_refuses_staff(self):
        old = db.session.get(User, self.old_id)
        old.set_role(str(DATA8), is_staff=True)
        db.session.commit()
        body = self.merge()
        self.assertFalse(body["success"])
        self.assertIn("on staff", body["message"])

    def test_refuses_someone_from_another_course(self):
        other = User(email="elsewhere@test", name="Elsewhere")
        other.set_role(str(DATA8), is_staff=False)
        db.session.add(other)
        db.session.commit()
        body = self.merge("elsewhere@test")
        self.assertFalse(body["success"])
        self.assertIn("isn't a student in this course", body["message"])

    def test_refuses_merging_into_someone_not_a_student_here(self):
        body = self.merge(new_email="staff@test")
        self.assertFalse(body["success"])
        self.assertIn("isn't a student in this course", body["message"])

    def test_refuses_unknown_and_identical_emails(self):
        self.assertIn("No one", self.merge("nobody@test")["message"])
        self.assertIn("No one", self.merge(new_email="nobody@test")["message"])
        self.assertIn("same student", self.merge("old@test", "OLD@test")["message"])

    def test_admins_only(self):
        staff = db.session.get(User, self.staff_id)
        staff.canvas_courses = {str(CS61A): canvas_course("CS 61A", staff=True)}
        staff.set_role("cs61a", is_staff=True)
        db.session.commit()
        self.assertFalse(self.merge()["success"])
        self.assertIsNotNone(db.session.get(User, self.old_id))
