from canvasapi import Canvas
from flask import current_app

from course import get_canvas_course_id

# Requested at login. Must be a subset of the scopes on the sections Canvas developer key.
SCOPES = [
    "url:GET|/api/v1/users/:id",
    "url:GET|/api/v1/courses/:id",
    "url:GET|/api/v1/users/:user_id/courses",
    "url:GET|/api/v1/users/:user_id/profile",
    "url:GET|/api/v1/courses/:course_id/enrollments",
    "url:GET|/api/v1/accounts/:account_id/users",
]

# Enrollment types as the user courses endpoint reports them.
STAFF_ENROLLMENT_TYPES = {"ta", "teacher"}


def _client(access_token: str) -> Canvas:
    return Canvas(current_app.config["CANVAS_SERVER_URL"], access_token)


def get_profile(user_id, access_token: str) -> dict:
    """Canvas profile with ``primary_email``, ``name`` and ``short_name``."""
    return _client(access_token).get_user(user_id).get_profile()


def _start_at(course):
    """The term's start, else the course's own start, else its creation, like seating."""
    term = getattr(course, "term", None) or {}
    return term.get("start_at") or getattr(course, "start_at", None) or getattr(course, "created_at", None)


def get_user_courses(user_id, access_token: str) -> dict:
    """The user's active Canvas courses and their role in each.

    Returns ``{str(course id): {"name", "code", "start_at", "is_staff", "is_admin",
    "is_student"}}``. Staff are TAs and Teachers; admins are Teachers and Lead TAs.
    """
    courses = {}
    for c in _client(access_token).get_user(user_id).get_courses(
        enrollment_state="active", include=["term"], per_page=100
    ):
        enrollments = getattr(c, "enrollments", None) or []
        if not enrollments or not hasattr(c, "course_code"):
            continue  # courses the user can't see, or restricted by date
        types = {e["type"] for e in enrollments}
        roles = {e.get("role") for e in enrollments}
        courses[str(c.id)] = {
            "name": c.name,
            "code": c.course_code,
            "start_at": _start_at(c),
            "is_staff": bool(types & STAFF_ENROLLMENT_TYPES),
            "is_admin": "teacher" in types or "Lead TA" in roles,
            "is_student": "student" in types,
        }
    return courses


def get_student_from_email(email: str, access_token: str):
    """Name of the student in the current course with login ``email``, or None."""
    course = _client(access_token).get_course(get_canvas_course_id())
    for enrollment in course.get_enrollments(type=["StudentEnrollment"]):
        if enrollment.user["login_id"] == email:
            return enrollment.user["name"]
    return None
