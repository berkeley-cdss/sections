"""Only a section's TA and the course's admins can change the section (#46)."""

from server.models import Attendance, Section, Session, User, db
from tests.unit.support import CS61A, CourseTestCase, canvas_course


class SectionEditorTests(CourseTestCase):
    def setUp(self):
        super().setUp()
        self.other = User(email="other-ta@test", name="Other TA", canvas_id="20",
                          canvas_courses={str(CS61A): canvas_course("CS 61A", staff=True)})
        self.other.set_role("cs61a", is_staff=True)
        section = db.session.get(Section, self.section_id)
        section.staff = self.other
        section.students.append(db.session.get(User, self.known_id))
        session = Session(start_time=0, section_id=self.section_id, course="cs61a")
        db.session.add_all([self.other, session])
        db.session.commit()
        self.session_id = session.id

    def edits(self):
        section_id = str(self.section_id)
        return [
            ("update_section_description", {"section_id": section_id, "description": "Hi"}),
            ("update_section_call_link", {"section_id": section_id, "call_link": "https://evil.test"}),
            ("update_section_enrollment_code", {"section_id": section_id, "enrollment_code": "x"}),
            ("start_session", {"section_id": section_id, "start_time": 604800}),
            ("set_attendance", {"session_id": str(self.session_id), "students": "known@test",
                                "status": "absent"}),
            ("remove_student", {"student": "known@test", "section_id": section_id}),
            ("add_students", {"emails": "known@test", "section_id": section_id}),
        ]

    def test_other_staff_cannot_edit_the_section(self):
        for method, args in self.edits():
            with self.subTest(method=method):
                body = self.api(method, **args).get_json()
                self.assertFalse(body["success"])
                self.assertIn("Only this section's TA", body["message"])
        db.session.remove()
        section = db.session.get(Section, self.section_id)
        self.assertEqual((section.description, section.call_link, section.enrollment_code), ("", None, None))
        self.assertEqual([s.email for s in section.students], ["known@test"])
        self.assertEqual(Session.query.count(), 1)
        self.assertEqual(Attendance.query.count(), 0)

    def test_other_staff_can_still_view_the_section(self):
        self.assertTrue(self.api("fetch_section", section_id=str(self.section_id)).get_json()["success"])

    def test_the_sections_ta_can_edit_it(self):
        self.sign_in(db.session.get(User, self.other.id))
        for method, args in self.edits():
            with self.subTest(method=method):
                self.assertTrue(self.api(method, **args).get_json()["success"])

    def test_admins_can_edit_any_section(self):
        self.make_staff_admin()
        for method, args in self.edits():
            with self.subTest(method=method):
                self.assertTrue(self.api(method, **args).get_json()["success"])
