"""Looking up a course's staff in Canvas."""

from types import SimpleNamespace
from unittest.mock import patch

from flask import g

from server import canvas_service
from server.models import MAX_OFFERING_CANVAS_ID, Offering
from tests.unit.support import AppTestCase, CS61A, CourseTestCase


class CourseStaffLookupTests(CourseTestCase):
    def test_tas_and_teachers_with_admins_as_at_sign_in(self):
        def enrollment(user_id, type, role):
            return SimpleNamespace(user={"id": user_id}, type=type, role=role)

        client = patch("server.canvas_service._client").start()
        self.addCleanup(patch.stopall)
        get_enrollments = client.return_value.get_course.return_value.get_enrollments
        get_enrollments.return_value = [
            enrollment(1, "TaEnrollment", "TaEnrollment"),
            enrollment(2, "TaEnrollment", "Lead TA"),
            enrollment(3, "TeacherEnrollment", "TeacherEnrollment"),
            # Two enrollments (e.g. two sections): admin if either is.
            enrollment(4, "TaEnrollment", "TaEnrollment"),
            enrollment(4, "TeacherEnrollment", "TeacherEnrollment"),
        ]
        with self.app.test_request_context():
            g.offering = Offering.query.filter_by(canvas_id=CS61A).one()
            staff = canvas_service.get_course_staff("token")
        self.assertEqual(staff, {"1": False, "2": True, "3": True, "4": True})
        client.return_value.get_course.assert_called_once_with(CS61A)
        # Invited staff too, and a page size that fits most courses' staff.
        get_enrollments.assert_called_once_with(type=["TaEnrollment", "TeacherEnrollment"],
                                                state=["active", "invited"], per_page=100)


class UserCoursesTests(AppTestCase):
    def test_skips_courses_whose_ids_are_too_big(self):
        """Canvas gives a course on another shard a global ID, too big for
        offerings.canvas_id, so sign-in leaves it out."""
        def course(course_id):
            return SimpleNamespace(id=course_id, name=f"Course {course_id}", course_code="C",
                                   start_at=None, created_at=None, enrollments=[{"type": "student", "role": "S"}])

        client = patch("server.canvas_service._client").start()
        self.addCleanup(patch.stopall)
        client.return_value.get_user.return_value.get_courses.return_value = [
            course(1527317), course(MAX_OFFERING_CANVAS_ID), course(30000002702310)]
        with self.app.app_context():
            courses = canvas_service.get_user_courses(1, "token")
        self.assertEqual(set(courses), {"1527317", str(MAX_OFFERING_CANVAS_ID)})


class FakeCanvasCourseStaffTests(AppTestCase):
    config = {"MOCK_CANVAS": True}

    def test_fake_canvas_answers_the_lookup(self):
        with self.app.test_request_context():
            g.offering = Offering(canvas_id=1234567, key="1234567", name="Fake")
            self.assertEqual(canvas_service.get_course_staff("token"), {"123456": False, "567890": True})

    def test_invited_staff_count_but_not_other_states(self):
        enrollments = {
            "123456": {"1234567": {"enrollments": [
                {"type": "ta", "role": "TaEnrollment", "enrollment_state": "invited"}]}},
            "567890": {"1234567": {"enrollments": [
                {"type": "teacher", "role": "TeacherEnrollment", "enrollment_state": "completed"}]}},
        }
        with self.app.test_request_context(), patch.dict("server.fake_canvas.FAKE_ENROLLMENTS", enrollments, clear=True):
            g.offering = Offering(canvas_id=1234567, key="1234567", name="Fake")
            self.assertEqual(canvas_service.get_course_staff("token"), {"123456": False})
