"""Which course the current request belongs to.

Course pages and APIs live under /offerings/<canvas course id>/ (see state.py);
load_course resolves that ID to a Course row for the rest of the request.
"""

from flask import abort, g

from models import Course

# Matches seating's offering URLs.
COURSE_URL_PREFIX = "/offerings/<int:canvas_course_id>"


def load_course(canvas_course_id: int):
    course = Course.query.filter_by(canvas_id=canvas_course_id).one_or_none()
    if course is None:
        abort(404, "Sections isn't set up for this course yet. If this is unexpected, ask your course staff.")
    g.course = course


def current_course() -> Course:
    return g.course


def in_course() -> bool:
    return "course" in g


def get_canvas_course_id() -> int:
    return g.course.canvas_id


def get_course() -> str:
    """The key stored in each row's ``course`` column."""
    return g.course.key


def get_course_name() -> str:
    return g.course.display_name
