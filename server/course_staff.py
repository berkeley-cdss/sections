"""Who can be a section's TA in the current offering.

Someone's role here comes from the Canvas roles saved at their last sign-in,
which can be out of date: last semester's student may be on staff in a course
that's new since. When the saved roles don't put someone on staff, StaffCheck
asks Canvas, with the signed-in admin's token.
"""

from canvasapi.exceptions import Forbidden, InvalidAccessToken, Unauthorized
from flask import current_app
from flask_login import current_user

from server import canvas_service
from server.canvas_tokens import current_token
from server.models import Failure, User
from server.offering import current_offering, get_canvas_course_id, get_course


def can_teach_here(user: User) -> bool:
    """Whether ``user`` can be assigned a section in this offering, by their
    saved roles.

    Their role in an offering is only brought up to date with Canvas when they
    open its pages, so for anyone who has signed in, go by their Canvas roles
    from their last sign-in instead. People imported from a spreadsheet who
    haven't signed in only have their role here. Global admins count only
    where they're on staff in Canvas, not in every offering."""
    if user.canvas_id is not None:
        roles = user.canvas_roles_in(get_canvas_course_id())
        return roles is not None and roles[0]
    return get_course() in user.staff_offerings


def add_staff_role(user: User):
    """Make someone can_teach_here allows staff here, if they aren't yet: they're
    on staff in Canvas, but haven't opened this course here since."""
    if get_course() in user.staff_offerings:
        return
    roles = user.canvas_roles_in(get_canvas_course_id()) if user.canvas_id is not None else None
    user.set_role(get_course(), is_staff=True, is_admin=roles is not None and roles[1])


def save_canvas_staff_role(user: User, is_admin: bool):
    """Record that Canvas lists ``user`` as staff here now, in the roles saved at
    sign-in, so their next request (sync_offering_role) and later checks agree."""
    offering = current_offering()
    key = str(offering.canvas_id)
    courses = user.canvas_courses or {}
    entry = dict(courses.get(key) or {"name": offering.name, "code": offering.code,
                                      "start_at": offering.start_at, "is_student": False})
    entry.update(is_staff=True, is_admin=is_admin)
    # A new dict, so SQLAlchemy sees the JSON column change.
    user.canvas_courses = {**courses, key: entry}
    user.set_role(get_course(), is_staff=True, is_admin=is_admin)


def admin_canvas_token() -> str | None:
    """The signed-in admin's Canvas token in this browser, if it's current."""
    return current_token(current_user) if current_user.is_authenticated else None


class StaffCheck:
    """Checks whether people are on staff here, asking Canvas at most once."""

    def __init__(self):
        self._canvas_staff: dict[str, bool] | None = None

    def check(self, user: User, email: str):
        """Make ``user`` staff here, or raise a Failure saying why they can't be."""
        if can_teach_here(user):
            add_staff_role(user)
            return
        if user.canvas_id is None:
            raise Failure(f"{email} isn't on staff in this course. If they're on staff in bCourses now, "
                          "they need to sign in to Sections once first.")
        is_admin = self.canvas_staff().get(user.canvas_id)
        if is_admin is None:
            raise Failure(f"{email} isn't on staff in this course.")
        save_canvas_staff_role(user, is_admin)

    def canvas_staff(self) -> dict[str, bool]:
        """The course's staff in Canvas now (see canvas_service.get_course_staff)."""
        if self._canvas_staff is None:
            sign_in_again = Failure(
                "Checking with bCourses whether someone is on staff needs a recent Canvas sign-in "
                "in this browser. Log out and sign in with Canvas again, then retry.")
            access_token = admin_canvas_token()
            if access_token is None:
                raise sign_in_again
            try:
                self._canvas_staff = canvas_service.get_course_staff(access_token)
            except InvalidAccessToken:
                raise sign_in_again
            except (Unauthorized, Forbidden):
                raise Failure("Your bCourses account can't see this course's TAs and teachers, "
                              "so Sections can't check whether someone is on staff.")
            except Exception:
                current_app.logger.exception("Couldn't get the course's staff from Canvas")
                raise Failure("Sections couldn't reach bCourses to check whether someone is on staff. "
                              "Try again in a few minutes.")
        return self._canvas_staff
