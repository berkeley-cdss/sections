"""Adding students to a section by email, which looks unknown students up in bCourses."""

from unittest.mock import patch

from canvasapi.exceptions import InvalidAccessToken
from flask import g

from models import Offering, Section, User, db
from tests.unit.support import CS61A, CourseTestCase


class AddStudentsTests(CourseTestCase):
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

    def test_email_lookups_ignore_case(self):
        with patch("state.canvas_service.get_student_from_email") as lookup:
            self.assertTrue(self.add_students("KNOWN@Test")["success"])
        lookup.assert_not_called()  # found the existing person, no Canvas lookup
        self.assertEqual(User.query.count(), 2)
