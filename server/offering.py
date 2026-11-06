"""Which course the current request belongs to.

Offering pages and APIs live under /offerings/<canvas course id>/ (see state.py);
load_offering resolves that ID to an Offering row for the rest of the request.
"""

from flask import abort, g

from server.models import Offering, User

# Matches seating's offering URLs.
OFFERING_URL_PREFIX = "/offerings/<int:canvas_course_id>"


def load_offering(canvas_course_id: int):
    offering = Offering.query.filter_by(canvas_id=canvas_course_id).one_or_none()
    if offering is None:
        abort(404, "Sections isn't set up for this course yet. If this is unexpected, ask your course staff.")
    g.offering = offering


def current_offering() -> Offering:
    return g.offering


def in_offering() -> bool:
    return "offering" in g


def get_canvas_course_id() -> int:
    return g.offering.canvas_id


def get_course() -> str:
    """The key stored in each row's ``course`` column."""
    return g.offering.key


def get_course_name() -> str:
    return g.offering.display_name


def can_teach_here(user: User) -> bool:
    """Whether ``user`` can be assigned a section in this offering.

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
