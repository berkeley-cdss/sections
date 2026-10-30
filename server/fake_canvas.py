"""A stand-in for canvasapi's Canvas, backed by fake_canvas_data, as in seating's
server/services/canvas/fake_canvas.py. It answers only the calls canvas_service makes."""

from __future__ import annotations

from types import SimpleNamespace

from fake_canvas_data import FAKE_COURSES, FAKE_ENROLLMENTS, FAKE_USERS


class FakeCanvas:
    def get_user(self, canvas_id) -> FakeUser:
        return FakeUser(canvas_id)

    def get_course(self, canvas_id) -> FakeCourse:
        return FakeCourse(canvas_id)


class FakeUser:
    def __init__(self, canvas_id):
        user = FAKE_USERS[str(canvas_id)]
        self.id = user["id"]
        self.name = user["name"]
        self.short_name = user["short_name"]
        self.email = user["email"]
        self.sis_user_id = user["sis_user_id"]
        self.login_id = user["login_id"]

    def get_profile(self) -> dict:
        return {"id": self.id, "name": self.name, "short_name": self.short_name,
                "primary_email": self.email, "login_id": self.login_id}

    def get_courses(self, *, enrollment_state="active", include=(), per_page=100) -> list[FakeCourse]:
        return [FakeCourse(course_id, course["enrollments"])
                for course_id, course in FAKE_ENROLLMENTS.get(str(self.id), {}).items()
                if not enrollment_state or any(
                    e["enrollment_state"] == enrollment_state for e in course["enrollments"])]


class FakeCourse:
    def __init__(self, canvas_id, enrollments=()):
        course = FAKE_COURSES[str(canvas_id)]
        self.id = course["id"]
        self.name = course["name"]
        self.course_code = course["course_code"]
        self.sis_course_id = course["sis_course_id"]
        # canvasapi's Course.start_at is an ISO 8601 string, as here.
        self.start_at = course["start_at"]
        self.enrollments = list(enrollments)

    def get_enrollments(self, *, type=()) -> list[SimpleNamespace]:
        """Enrollments in this course, as the course enrollments endpoint gives
        them: ``type`` is e.g. "StudentEnrollment", and ``user`` a dict."""
        found = []
        for user_id, courses in FAKE_ENROLLMENTS.items():
            for e in courses.get(str(self.id), {}).get("enrollments", []):
                # "student" in the user courses endpoint is "StudentEnrollment" here.
                enrollment_type = e["type"].capitalize() + "Enrollment"
                if not type or enrollment_type in type:
                    user = FAKE_USERS[user_id]
                    found.append(SimpleNamespace(type=enrollment_type, role=e["role"], user={
                        "id": user["id"], "name": user["name"], "short_name": user["short_name"],
                        "login_id": user["login_id"], "sis_user_id": user["sis_user_id"]}))
        return found
