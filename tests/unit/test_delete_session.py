"""A session started by mistake can be deleted, with its attendance (#96).
Who may delete one is tested with the other section edits, in
test_section_permissions."""

from server.models import Attendance, AttendanceStatus, Section, Session, User, db
from tests.unit.support import CourseTestCase, DATA8


class DeleteSessionTests(CourseTestCase):
    def add_session(self, section_id, course, start_time=0, attendance=True):
        session = Session(start_time=start_time, section_id=section_id, course=course)
        db.session.add(session)
        if attendance:
            db.session.add(Attendance(status=AttendanceStatus.present, session=session,
                                      student=db.session.get(User, self.known_id), course=course))
        db.session.commit()
        return session.id

    def test_deletes_the_session_and_its_attendance(self):
        doomed = self.add_session(self.section_id, "cs61a")
        kept = self.add_session(self.section_id, "cs61a", start_time=604800)

        body = self.api("delete_session", session_id=str(doomed)).get_json()

        self.assertTrue(body["success"], body)
        # The section comes back without it, for the page to show.
        self.assertEqual([s["id"] for s in body["data"]["sessions"]], [kept])
        db.session.remove()
        self.assertIsNone(db.session.get(Session, doomed))
        self.assertEqual([a.session_id for a in Attendance.query.all()], [kept])
        self.assertIsNotNone(db.session.get(Section, self.section_id))

    def test_deletes_a_session_with_no_attendance(self):
        session_id = self.add_session(self.section_id, "cs61a", attendance=False)
        self.assertTrue(self.api("delete_session", session_id=str(session_id)).get_json()["success"])
        self.assertEqual(Session.query.count(), 0)

    def test_cannot_delete_another_offerings_session(self):
        self.make_staff_admin()
        session_id = self.add_session(self.data8_section_id, str(DATA8))
        # The error handler reports the missing session as a 404.
        self.assertEqual(self.api("delete_session", session_id=str(session_id)).status_code, 404)
        self.assertEqual(Session.query.count(), 1)
        self.assertEqual(Attendance.query.count(), 1)

    def test_students_cannot_delete_sessions(self):
        session_id = self.add_session(self.section_id, "cs61a")
        self.sign_in(db.session.get(User, self.known_id))
        self.assertFalse(self.api("delete_session", session_id=str(session_id)).get_json()["success"])
        self.assertEqual(Session.query.count(), 1)
