import requests
from canvasapi import Canvas
from flask import current_app

from server.fake_canvas import FakeCanvas
from server.offering import get_canvas_course_id

# Requested at login. Must be a subset of the scopes on the sections Canvas developer key.
SCOPES = [
    "url:GET|/api/v1/users/:id",
    "url:GET|/api/v1/courses/:id",
    "url:GET|/api/v1/users/:user_id/courses",
    "url:GET|/api/v1/users/:user_id/profile",
    "url:GET|/api/v1/courses/:course_id/enrollments",
    "url:GET|/api/v1/courses/:course_id/users",
    "url:GET|/api/v1/accounts/:account_id/users",
]

# Enrollment types as the user courses endpoint reports them.
STAFF_ENROLLMENT_TYPES = {"ta", "teacher"}


def is_mock_canvas() -> bool:
    """Whether to use the fake Canvas (fake_canvas.py) rather than bCourses, as in
    seating. Never in production, whatever the config says."""
    return bool(current_app.config.get("MOCK_CANVAS")) and current_app.config.get("APP_ENV") != "production"


def _client(access_token: str) -> Canvas | FakeCanvas:
    if is_mock_canvas():
        return FakeCanvas()
    return Canvas(current_app.config["CANVAS_SERVER_URL"], access_token)


def revoke_token(access_token: str):
    """Ask Canvas to revoke an access token, so it stops working before it
    expires. Best effort: signing out mustn't fail because Canvas is down, and
    the token expires within an hour regardless."""
    if is_mock_canvas():
        return
    try:
        response = requests.delete(current_app.config["CANVAS_SERVER_URL"] + "login/oauth2/token",
                                   headers={"Authorization": f"Bearer {access_token}"}, timeout=5)
        response.raise_for_status()
    except requests.RequestException as error:
        current_app.logger.warning("Couldn't revoke a Canvas access token: %s", error)


def get_profile(user_id, access_token: str) -> dict:
    """Canvas profile with ``primary_email``, ``name``, ``short_name`` (the display
    name) and, if the person shares them, ``pronouns``."""
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


def get_course_staff(access_token: str) -> dict[str, bool]:
    """The current course's staff in Canvas now: ``{str(canvas user id): is_admin}``.
    As in get_user_courses, TAs and Teachers are staff, and Teachers and Lead TAs
    are admins. Unlike there, invited enrollments count too, so staff added to
    the course can be given sections before they accept the invitation."""
    staff = {}
    course = _client(access_token).get_course(get_canvas_course_id())
    for enrollment in course.get_enrollments(type=["TaEnrollment", "TeacherEnrollment"],
                                             state=["active", "invited"], per_page=100):
        user_id = str(enrollment.user["id"])
        is_admin = enrollment.type == "TeacherEnrollment" or enrollment.role == "Lead TA"
        staff[user_id] = staff.get(user_id, False) or is_admin
    return staff


def get_roster(access_token: str) -> list[dict]:
    """The current course's students on bCourses, including those who haven't
    accepted their invitation yet: ``[{"canvas_id", "email", "name"}]``. The
    email is the one Canvas shares (their primary email, as at sign-in), or
    None if it shares none, and the name their display name. Waitlisted
    students are included when bCourses enrolls them as students.

    Unlike the enrollments endpoint, this lists each student once, however many
    of the course's sections (lecture, lab, discussion) they're enrolled in,
    and gives their email rather than their login (at Berkeley, a CalNet UID)."""
    course = _client(access_token).get_course(get_canvas_course_id())
    return [
        {"canvas_id": str(user.id), "email": getattr(user, "email", None) or None,
         "name": getattr(user, "short_name", None) or user.name}
        for user in course.get_users(enrollment_type=["student"], enrollment_state=["active", "invited"],
                                     include=["email"], per_page=100)
    ]


def get_student_from_email(email: str, access_token: str):
    """``(canvas user id, name)`` of the student in the current course with
    login ``email``, or None. The name is their display name, as at login."""
    course = _client(access_token).get_course(get_canvas_course_id())
    for enrollment in course.get_enrollments(type=["StudentEnrollment"]):
        user = enrollment.user
        if user["login_id"] == email:
            return str(user["id"]), user.get("short_name") or user["name"]
    return None
