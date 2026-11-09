import csv
import re
import time
from canvasapi.exceptions import Forbidden, InvalidAccessToken, Unauthorized

from io import StringIO
from datetime import datetime
from functools import wraps
from json import dumps
from urllib.parse import urlparse
from typing import List, Optional, Union
from zoneinfo import ZoneInfo
from server.import_sheet import parse_section_times

import flask
from flask import Blueprint, abort, g, jsonify, render_template, request, current_app
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.orm import joinedload, noload

from server import canvas_service
from server.canvas_tokens import current_token
from server.api_keys import audit_log, authenticate, create_key, init_api_keys, record_use, using_api_key
from server.login import sync_offering_role
from server.course_staff import StaffCheck, can_teach_here
from server.offering import OFFERING_URL_PREFIX, get_canvas_course_id, get_course, get_course_name, load_offering
from server.import_sheet import check_capacity, import_sections_from_url, import_enrollment_from_url, parse_capacity

from server.models import (
    ApiKey,
    Attendance,
    AttendanceStatus,
    CourseConfig,
    Failure,
    Section,
    Session,
    User,
    check_fits,
    db,
    find_or_add_person,
    offering_member,
    set_contains,
    user_section,
)

FIRST_WEEK_START = datetime(year=2022, month=6, day=27).timestamp()
ONE_WEEK = 60 * 60 * 24 * 7  # number of seconds in a week
IS_SUMMER = True
MAX_ABSENCES = 2
UNASSIGNED = "UNASSIGNED"


def staff_required(func):
    @wraps(func)
    @login_required
    def wrapped(**kwargs):
        if not current_user.is_staff:
            raise Failure("Only staff can perform this action")
        return func(**kwargs)

    return wrapped


def session_only(func):
    """Refuse requests made with an API key, e.g. so a leaked key can't make
    more keys that outlive revoking it."""
    @wraps(func)
    def wrapped(**kwargs):
        if using_api_key():
            raise Failure("This can't be done with an API key. Sign in to Sections instead.")
        return func(**kwargs)

    return wrapped


def admin_required(func):
    @wraps(func)
    @staff_required
    def wrapped(**kwargs):
        if not current_user.is_admin:
            raise Failure("Only course admins can perform this action.")
        return func(**kwargs)

    return wrapped


def check_can_edit(section: Section) -> None:
    """Only a section's TA and the course's admins may change it."""
    if section.staff_id != current_user.id and not current_user.is_admin:
        raise Failure("Only this section's TA or a course admin can change this section.")


def section_sorter(
    section: Section, enrollment_count: int, current_section_ids
) -> int:
    score = 0
    big = 10000
    if current_user.is_staff and section.staff_id is None:
        score -= big * 100
    if (
        section.staff_id == current_user.id
        or section.id in current_section_ids
    ):
        score -= big * 10
    spare_capacity = max(0, section.capacity - enrollment_count)
    if spare_capacity:
        score -= big * spare_capacity
    score += section.id
    return score


def parse_emails(emails):
    return re.split(r"[\s,]+", emails.strip())


def get_config() -> CourseConfig:
    return CourseConfig.query.filter_by(course=get_course()).one()


# The CourseConfig columns update_config may change: not its id or course.
CONFIG_SETTINGS = {column.name for column in CourseConfig.__table__.columns
                   if column.name.startswith("can_")} | {"message", "staff_url"}


def clean_url(label: str, value, column) -> str | None:
    """The URL to store, or None for no link. Only http(s) URLs, since the page
    links to it (a javascript: URL would run in the course's page). ``label``
    names it in error messages, and it must fit ``column``."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise Failure(f"{label} must be text")
    value = value.strip()
    if not value:
        return None
    check_fits(label, value, column)
    try:
        parsed = urlparse(value)
        ok = parsed.scheme.lower() in ("http", "https") and bool(parsed.hostname)
    except ValueError:  # e.g. an unclosed [ in the host
        ok = False
    if not ok or re.search(r"\s", value):
        raise Failure(f"{label} must be a web address starting with https:// or http://")
    return value


def add_student_helper(student: User, target_section: Section):
    # Only the target's offering matters; the person may be in other offerings too.
    sections = student.sections_in(target_section.course)
    if len(set([s.name for s in sections])) != len(sections):
        raise Failure("Student has multiple sections of the same type")

    # If user is already in a section of the same type, remove it and add target section
    for s in sections:
        if s.name == target_section.name:
            student.sections.remove(s)
            break
    student.sections.append(target_section)
    # SQLAlchemy 2.0 no longer cascades new objects into the session through backrefs.
    db.session.add(student)

def create_state_client(app: flask.Flask):
    # Every offering page and API lives under /offerings/<canvas course id>/.
    bp = Blueprint("offering", __name__, url_prefix=OFFERING_URL_PREFIX)
    init_api_keys(app)

    @bp.url_value_preprocessor
    def pull_course(endpoint, values):
        load_offering(values.pop("canvas_course_id"))

    @bp.url_defaults
    def add_course(endpoint, values):
        if "offering" in g:
            values.setdefault("canvas_course_id", g.offering.canvas_id)

    def api(handler):
        def wrapped():
            try:
                #return jsonify({"success": True, "data": handler(**request.json)})
                result = handler(**request.json)
                if isinstance(result, Failure):
                    return jsonify({"success": False, "message": str(result)})
                return jsonify({"success": True, "data": result})
            except Failure as failure:
                return jsonify({"success": False, "message": str(failure)})

        bp.add_url_rule(
            f"/api/{handler.__name__}", handler.__name__, wrapped, methods=["POST"]
        )

        def sudo_wrapped():
            api_key = authenticate()
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                abort(400, 'Send a JSON object: {"email": ..., "args": {...}}.')
            email, args = data.get("email"), data.get("args", {})
            if not isinstance(args, dict) or not (email is None or isinstance(email, str)):
                abort(400, '"args" must be an object, and "email" the email of a course member.')

            # The key's owner is an admin here (authenticate checked), so they
            # can act as anyone in this course, and no one outside it.
            sync_offering_role(api_key.owner)
            user = api_key.owner if email is None else offering_member(email=email)
            if user is None:
                abort(404, f"{email} isn't a member of this course.")
            # Act as this user for this request only, without touching the session.
            g._login_user = user
            g.api_key = api_key
            record_use(api_key, user, handler.__name__)
            try:
                return jsonify({"success": True, "data": handler(**args)})
            except Failure as failure:
                return jsonify({"success": False, "message": str(failure)})

        bp.add_url_rule(
            f"/api/sudo/{handler.__name__}",
            "sudo_" + handler.__name__,
            sudo_wrapped,
            methods=["POST"],
        )

        return handler

    @bp.route("/", endpoint="index")
    @bp.route("/history/")
    @bp.route("/lab/")
    @bp.route("/disc/")
    @bp.route("/tutoring/")
    @bp.route("/admin/")
    @bp.route("/section/<path:path>")
    @bp.route("/user/<path:path>")
    def generic(**_):
        # Loading the user here shows a signed-in visitor who isn't enrolled a
        # clear 403 page, instead of a broken app.
        current_user.is_authenticated
        return render_template("index.html", course=get_course_name())

    @api
    def refresh_state():
        """
        Returns overall information about the section in json.

        Backend API functions calling refresh_state should be called
        using the useAPI hook in frontend.
        """
        refresh_started_at = time.perf_counter()
        config = CourseConfig.query.filter_by(course=get_course()).one_or_none()

        out = {
            "enrolledSections": None,
            "taughtSections": None,
            "sections": [],
            "currentUser": None,
            "course": get_course_name(),
            # Signed out, only what the sign-in page shows.
            "config": {"message": config.message if config else ""},
            "serviceAccountEmail": None,
            "custom": None,
        }

        if current_user.is_authenticated:
            if config is None:
                config = CourseConfig(course=get_course())
                db.session.add(config)
                db.session.commit()
            out["config"] = config.json
            out["serviceAccountEmail"] = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_EMAIL")

            course = get_course()
            enrolled_sections = current_user.sections_in(course)
            taught_sections = [s for s in current_user.sections_taught if s.course == course]
            current_section_ids = {section.id for section in enrolled_sections}

            counts_started_at = time.perf_counter()
            enrollment_counts = dict(
                db.session.query(
                    user_section.c.section_id,
                    func.count(user_section.c.user_id),
                )
                .join(Section, Section.id == user_section.c.section_id)
                .filter(Section.course == course)
                .group_by(user_section.c.section_id)
                .all()
            )
            counts_ms = (time.perf_counter() - counts_started_at) * 1000

            def sort_key(section):
                return section_sorter(
                    section,
                    enrollment_counts.get(section.id, 0),
                    current_section_ids,
                )

            out["enrolledSections"] = [
                section.to_json(reveal_roster=True)
                for section in sorted(enrolled_sections, key=sort_key)
            ]
            out["taughtSections"] = [
                section.to_json(reveal_roster=True)
                for section in sorted(taught_sections, key=sort_key)
            ]
            sections_started_at = time.perf_counter()
            all_sections = (
                Section.query.options(noload(Section.students))
                .filter_by(course=course)
                .all()
            )
            sections_query_ms = (time.perf_counter() - sections_started_at) * 1000
            out["sections"] = [
                section.to_json(
                    include_students=False,
                    enrollment_count=enrollment_counts.get(section.id, 0),
                )
                for section in sorted(
                    all_sections,
                    key=sort_key,
                )
            ]
            # Keep attendance details without repeating full section rosters.
            out["currentUser"] = current_user.simple_json
            current_app.logger.info(
                "refresh_state role=%s sections=%d enrollments=%d "
                "counts_ms=%.1f sections_query_ms=%.1f total_ms=%.1f",
                "staff" if current_user.is_staff else "student",
                len(all_sections),
                sum(enrollment_counts.values()),
                counts_ms,
                sections_query_ms,
                (time.perf_counter() - refresh_started_at) * 1000,
            )

        return out

    @api
    @staff_required
    def fetch_section(section_id: Union[int, str]):
        """
        Returns info about a specific section in json.

        Backend API functions calling fetch_section should be
        called using the useSectionAPI hook in frontend.
        """
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).first()
        if not section:
            return {
                "id": section_id,
                "staff": None,
                "students": [],
                "enrollmentCount": 0,
                "description": "",
                "capacity": -1,
                "canSelfEnroll": False,
                "needsEnrollmentCode": False,
                "tags": "",
                "enrollmentCode": None,

                "name": "",
                "startTime": -1,
                "endTime": -1,
                "location": "",
                "callLink": ""
            }
        return section.full_json

    @api
    @login_required
    def join_section(target_section_id: str, enrollment_code: str = ""):
        target_section_id = int(target_section_id)
        # check if they can be added to the new section
        target_section: Section = Section.query.filter_by(
            id=target_section_id, course=get_course()
        ).one()

        # TODO: Really shouldn't be hard coded, but has to be with the code right now
        config = get_config()
        if target_section.name == "Discussion" and not config.can_students_join_disc:
            if any(current_user.sections_in(get_course())):
                raise Failure("Students cannot change their enrolled discussion!")
            else:
                raise Failure("Students cannot add themselves themselves to discussions!")
        if target_section.name == "Lab" and not config.can_students_join_lab:
            if any(current_user.sections_in(get_course())):
                raise Failure("Students cannot change their enrolled lab!")
            else:
                raise Failure("Students cannot add themselves themselves to labs!")
        if target_section.name == "Tutoring" and not config.can_students_join_tutoring:
            if any(current_user.sections_in(get_course())):
                raise Failure("Students cannot change their enrolled tutorial!")
            else:
                raise Failure("Students cannot add themselves themselves to tutorials!")

        # If student is already enrolled in a section of the same type/name (Lab/Disc/etc)
        if any(map(lambda section: section.name == target_section.name, current_user.sections_in(get_course()))):
            if target_section.name == "Discussion" and not config.can_students_change_disc:
                raise Failure("Students cannot change their enrolled discussion!")
            if target_section.name == "Lab" and not config.can_students_change_lab:
                raise Failure("Students cannot change their enrolled lab!")
            if target_section.name == "Tutoring" and not config.can_students_change_tutoring:
                raise Failure("Students cannot change their enrolled tutorials!")

        if target_section.capacity <= len(target_section.students):
            raise Failure("Target tutorial section is already full.")
        if (
            target_section.needs_enrollment_code
            and enrollment_code != target_section.enrollment_code
        ):
            raise Failure("Invalid enrollment code; cannot join section.")
        if not target_section.can_self_enroll:
            raise Failure("Cannot self-join this section.")
        # remove them from *all* old_sections for now

        add_student_helper(current_user, target_section)
        db.session.commit()

        return refresh_state()

    @api
    @login_required
    def leave_section(target_section_id: str):
        target_section_id = int(target_section_id)

        target_section: Section = Section.query.filter_by(
            id=target_section_id, course=get_course()
        ).one()

        # TODO: Really shouldn't be hard coded, but has to be with the code right now
        config = get_config()
        if target_section.name == "Discussion" and not config.can_students_change_disc:
            raise Failure("Students cannot remove themselves from discussions!")
        if target_section.name == "Lab" and not config.can_students_change_lab:
            raise Failure("Students cannot remove themselves from labs!")
        if target_section.name == "Tutoring" and not config.can_students_change_tutoring:
            raise Failure("Students cannot remove themselves from tutorials!")

        try:
            current_user.sections.remove(target_section)
        except:
            raise Failure("Removing student from section failed")
        db.session.commit()
        return refresh_state()

    @api
    @login_required
    def leave_all_sections():
        config = get_config()
        can_change = {
            "Lab": config.can_students_change_lab,
            "Discussion": config.can_students_change_disc,
            "Tutoring": config.can_students_change_tutoring,
        }
        course_sections = current_user.sections_in(get_course())
        if not all(can_change.get(s.name, True) for s in course_sections):
            raise Failure("Students cannot remove themselves from sections!")

        current_user.sections = [s for s in current_user.sections if s not in course_sections]

        db.session.commit()
        return refresh_state()

    @api
    @staff_required
    def claim_section(section_id: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        if section.name == "Lab":
            if not get_config().can_tutors_change_lab:
                raise Failure("Tutors cannot add themselves to labs!")
        elif section.name == "Discussion":
            if not get_config().can_tutors_change_disc:
                raise Failure("Tutors cannot add themselves to discussions!")
        elif section.name == "Tutoring":
            if not get_config().can_tutors_change_tutoring:
                raise Failure("Tutors cannot add themselves to tutoring sections!")

        if section.staff:
            raise Failure("Section is already claimed!")
        section.staff = current_user
        db.session.commit()
        return refresh_state()

    @api
    @staff_required
    def unassign_section(section_id: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        if section.staff is None:
            raise Failure("Section is already unassigned!")
        if section.staff.email == current_user.email:
            if (section.name == "Lab" and not get_config().can_tutors_change_lab) or \
               (section.name == "Discussion" and not get_config().can_tutors_change_disc) or \
               (section.name == "Tutoring" and not get_config().can_tutors_change_tutoring):
                raise Failure("Tutors cannot remove themselves from sections!")
        else:
            if (section.name == "Lab" and not get_config().can_tutors_reassign_lab) or \
               (section.name == "Discussion" and not get_config().can_tutors_reassign_disc) or \
               (section.name == "Tutoring" and not get_config().can_tutors_reassign_tutoring):
                raise Failure("Tutors cannot remove other tutors from sections!")
        section.staff = None
        db.session.commit()
        return refresh_state()

    @api
    @staff_required
    def update_section_description(section_id: str, description: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        check_can_edit(section)
        check_fits("Your introduction", description, Section.description)
        section.description = description
        db.session.commit()
        return refresh_state()

    @api
    @staff_required
    def update_section_call_link(section_id: str, call_link: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        check_can_edit(section)
        section.call_link = clean_url("The call link", call_link, Section.call_link)
        db.session.commit()
        return refresh_state()

    @api
    @staff_required
    def update_section_enrollment_code(section_id: str, enrollment_code: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        check_can_edit(section)
        check_fits("The enrollment code", enrollment_code, Section.enrollment_code)
        section.enrollment_code = enrollment_code
        db.session.commit()
        return refresh_state()

    @api
    @admin_required
    def update_section_location(section_id: str, new_location: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        check_fits("Location", new_location, Section.location)
        section.location = new_location
        db.session.commit()
        return fetch_section(section_id=section_id)

    @api
    @admin_required
    def update_section_time(section_id: str, day: str, start_time: str, end_time: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        section.start_time, section.end_time = parse_section_times(day, start_time, end_time)
        db.session.commit()
        return fetch_section(section_id=section_id)

    @api
    @admin_required
    def update_section_tags(section_id: str, tags: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        section.tags = tags.split(",")
        check_fits("Tags", section.tag_string, Section.tag_string)
        db.session.commit()
        return fetch_section(section_id=section_id)

    @api
    @admin_required
    def update_section_capacity(section_id: str, capacity: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        capacity = parse_capacity(str(capacity))
        check_capacity(section, capacity)
        section.capacity = capacity
        db.session.commit()
        return fetch_section(section_id=section_id)

    @api
    @admin_required
    def list_staff():
        """Everyone who can be assigned a section here: by can_teach_here, plus
        anyone in Sections whom Canvas lists as staff now. If Canvas can't be
        asked (e.g. no current Canvas token), only the former."""
        canvas_key = f'"{get_canvas_course_id()}"'
        candidates = User.query.filter(
            set_contains(User.staff_offerings, get_course())
            # Narrows the search to people with this course in their Canvas
            # courses; can_teach_here checks their role there.
            | db.cast(User.canvas_courses, db.Text).contains(canvas_key, autoescape=True)
        ).all()
        staff = {user for user in candidates if can_teach_here(user)}
        try:
            canvas_staff = StaffCheck().canvas_staff()
        except Failure:
            canvas_staff = {}  # e.g. no current Canvas token; StaffCheck logs unexpected errors
        if canvas_staff:
            staff.update(User.query.filter(User.canvas_id.in_(list(canvas_staff))).all())
        return [
            {"id": str(user.id), "name": user.name, "email": user.email}
            for user in sorted(staff, key=lambda user: user.name.lower())
        ]

    @api
    @admin_required
    def update_section_staff(section_id: str, staff_id: str):
        """Assign the section to the staff member with this id, or leave it
        unassigned if the id is blank."""
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        if staff_id:
            staff = db.session.get(User, int(staff_id))
            if staff is None:
                raise Failure("That person isn't on staff in this course.")
            StaffCheck().check(staff, staff.email)
            section.staff = staff
        else:
            section.staff = None
        db.session.commit()
        return fetch_section(section_id=section_id)

    @api
    @staff_required
    def start_session(section_id: str, start_time: int):
        section_id = int(section_id)
        check_can_edit(Section.query.filter_by(id=section_id, course=get_course()).one())
        existing_session = Session.query.filter_by(
            start_time=start_time, section_id=section_id
        ).first()
        if existing_session is None:
            db.session.add(
                Session(
                    start_time=start_time,
                    section_id=section_id,
                    course=get_course(),
                )
            )
            db.session.commit()
        return fetch_section(section_id=section_id)

    @api
    @staff_required
    def set_attendance(session_id: str, students: str, status: Optional[str]):
        session_id = int(session_id)
        session = Session.query.filter_by(id=session_id, course=get_course()).one()
        check_can_edit(session.section)
        status = AttendanceStatus[status]
        for email in parse_emails(students):
            student = offering_member(email=email)
            if student is None:
                raise Failure(f"Student {email} is not enrolled")
            Attendance.query.filter_by(session_id=session_id, student=student).delete()
            if student is not None and status is not None:
                db.session.add(
                    Attendance(
                        status=status,
                        session_id=session_id,
                        student=student,
                        course=get_course(),
                    )
                )
        db.session.commit()
        return fetch_section(section_id=session.section_id)

    @api
    @admin_required
    def update_config(**kwargs):
        config = get_config()
        unknown = set(kwargs) - CONFIG_SETTINGS
        if unknown:
            raise Failure(f"Unknown setting: {', '.join(sorted(unknown))}")
        check_fits("The welcome message", kwargs.get("message"), CourseConfig.message)
        if "staff_url" in kwargs:
            kwargs["staff_url"] = clean_url("The staff page URL", kwargs["staff_url"], CourseConfig.staff_url)
        for key, value in kwargs.items():
            setattr(config, key, value)
        db.session.commit()
        return refresh_state()

    @api
    @staff_required
    def remove_student(student: str, section_id: str):
        section_id = int(section_id)
        student = offering_member(email=student)
        if student is None:
            raise Failure("That student is not enrolled in this course")
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        check_can_edit(section)
        student.sections.remove(section)
        db.session.commit()
        return fetch_section(section_id=section_id)

    @api
    @admin_required
    def remove_students(students: str):
        for s in parse_emails(students):
            student = offering_member(email=s)
            if student:
                # Only this offering's sections; the person may be in others.
                student.sections = [sec for sec in student.sections if sec.course != get_course()]
        db.session.commit()
        return refresh_state()

    @api
    @admin_required
    def remove_students_from_tutoring(students: str):
        for s in parse_emails(students):
            student = offering_member(email=s)
            if student:
                student.sections = [
                    sec for sec in student.sections
                    if not (sec.course == get_course() and sec.name == "Tutoring")
                ]
        db.session.commit()
        return refresh_state()

    def bcourses_roster() -> list[dict]:
        """The course's students on bCourses (canvas_service.get_roster), or a
        Failure saying why they can't be read."""
        sign_in_again = Failure("Syncing with bCourses needs a recent Canvas sign-in in this browser. "
                                "Log out and sign in with Canvas again, then retry.")
        access_token = current_token(current_user)
        if access_token is None:
            raise sign_in_again
        try:
            roster = canvas_service.get_roster(access_token)
        except InvalidAccessToken:
            raise sign_in_again
        except (Unauthorized, Forbidden):
            raise Failure("Your bCourses account can't see this course's students, so Sections can't sync them.")
        except Exception:
            current_app.logger.exception("Couldn't get the course's students from Canvas")
            raise Failure("Sections couldn't reach bCourses to sync students. Try again in a few minutes.")
        if not roster:
            # More likely a problem in bCourses than a course with no students;
            # syncing would remove everyone.
            raise Failure("bCourses listed no students in this course, so nothing was changed.")
        return roster

    def sync_bcourses_changes():
        """Make this offering's students the course's students on bCourses,
        without committing. Returns a dict of lists: the emails of students
        ``added`` and ``removed``; the emails of students on the roster who
        weren't added because the email belongs to someone here with another
        bCourses account (``skipped``); and the names of students who weren't
        added because bCourses didn't share their email (``no_email``)."""
        course = get_course()
        canvas_key = str(get_canvas_course_id())
        started_at = time.perf_counter()
        roster = bcourses_roster()
        fetched_at = time.perf_counter()

        # Everyone the roster could match, in two queries rather than one or two per student.
        by_canvas_id = {user.canvas_id: user for user in
                        User.query.filter(User.canvas_id.in_([entry["canvas_id"] for entry in roster]))}
        emails = {entry["email"].strip().lower() for entry in roster if entry["email"]}
        by_email = {user.email.lower(): user for user in User.query.filter(func.lower(User.email).in_(emails))}

        on_roster = set()
        changes = {"added": [], "removed": [], "skipped": [], "no_email": []}
        for entry in roster:
            person = by_canvas_id.get(entry["canvas_id"])
            if person is None:
                email = (entry["email"] or "").strip()
                if not email:
                    changes["no_email"].append(entry["name"])
                    continue
                person = by_email.get(email.lower())
                if person is not None and person.canvas_id is not None:
                    # Someone else here has this email, linked to another bCourses
                    # account; whether they're the same person is for a person to say.
                    changes["skipped"].append(email)
                    continue
                if person is None:
                    person = User(email=email, name=entry["name"])
                    db.session.add(person)
                    by_email[email.lower()] = person
                # Imported from a spreadsheet or added by email: link them to
                # their bCourses account, as signing in would.
                person.canvas_id = entry["canvas_id"]
                by_canvas_id[entry["canvas_id"]] = person
            on_roster.add(person)
            if course in person.staff_offerings:
                continue  # roles on staff come from their own sign-in
            if course not in person.student_offerings:
                person.set_role(course, is_staff=False)
                changes["added"].append(person.email)

        for student in User.query.filter(set_contains(User.student_offerings, course)).all():
            if student in on_roster:
                continue
            student.student_offerings = student.student_offerings - {course}
            # Out of this offering's sections; their attendance records stay.
            student.sections = [section for section in student.sections if section.course != course]
            if canvas_key in (student.canvas_courses or {}):
                # Otherwise their next request (sync_offering_role) would add
                # them back from the roles saved at their last sign-in. A new
                # dict, so SQLAlchemy sees the JSON column change.
                student.canvas_courses = {k: v for k, v in student.canvas_courses.items() if k != canvas_key}
            changes["removed"].append(student.email)

        current_app.logger.info("bCourses sync in %s: %d students on the roster, read from Canvas in %.1fs, "
                                "matched in %.1fs", course, len(roster), fetched_at - started_at,
                                time.perf_counter() - fetched_at)
        return {key: sorted(values) for key, values in changes.items()}

    @api
    @admin_required
    @session_only
    def preview_bcourses_sync():
        """What sync_bcourses would change now, changing nothing."""
        try:
            return sync_bcourses_changes()
        finally:
            db.session.rollback()

    @api
    @admin_required
    @session_only
    def sync_bcourses():
        """Add the course's students on bCourses (including invited ones) to this
        offering, and remove students no longer there from it and its sections."""
        changes = sync_bcourses_changes()
        db.session.commit()
        added, removed, skipped, no_email = (changes[key] for key in ("added", "removed", "skipped", "no_email"))
        current_app.logger.info("bCourses sync in %s by %s: added %d, removed %d (%s), skipped %d, no email %d",
                                get_course(), current_user.email, len(added), len(removed),
                                ", ".join(removed), len(skipped), len(no_email))
        message = f"Added {len(added)} students and removed {len(removed)}."
        if skipped:
            message += (f" Didn't add {len(skipped)} whose email belongs to a different bCourses account "
                        "in Sections: " + ", ".join(skipped) + ".")
        if no_email:
            message += (f" Didn't add {len(no_email)} whose email bCourses didn't share: "
                        + ", ".join(no_email) + ".")
        return {**refresh_state(), "custom": {"message": message}}

    @api
    @staff_required
    def add_students(emails: str, section_id: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        check_can_edit(section)
        access_token = current_token(current_user)
        for email in parse_emails(emails):
            student = offering_member(email=email)
            if student is not None and student.is_staff:
                raise Failure("Attempted to add staff: {student.name}")
            if student is None:
                # Existing students need no Canvas token; unknown students need a fresh login.
                if access_token is None:
                    raise Failure(
                        "Canvas authorization has expired. Please log out and sign in "
                        "with Canvas again, then retry adding students."
                    )
                try:
                    found = canvas_service.get_student_from_email(email, access_token)
                except (InvalidAccessToken, Unauthorized):
                    raise Failure(
                        "Canvas authorization is no longer valid. Please log out and sign in "
                        "with Canvas again, then retry adding students."
                    )
                except Exception:
                    return Failure(
                        "Adding student failed. Make sure the email is correct "
                        "and belongs to this class."
                    )

                if not found:
                    raise Failure("Could not find email that belongs to this class")
                canvas_id, canvasname = found
                student = find_or_add_person(email, canvasname, canvas_id=canvas_id)
                student.set_role(get_course(), is_staff=False)
            add_student_helper(student, section)
        db.session.commit()
        return fetch_section(section_id=section_id)

    @api
    @admin_required
    def delete_section(section_id: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        if section.students:
            raise Failure("Cannot delete a non-empty section")
        db.session.delete(section)
        db.session.commit()

        return refresh_state()

    @api
    @admin_required
    def export_attendance():
        return export_helper()

    def export_helper():
        stringify = dumps
        attendances = dict()
        emails = set()
        course = get_course()
        for user in (
            # Students no longer in the course (e.g. removed by a bCourses sync)
            # keep their attendance, so they're included too.
            User.query.filter(set_contains(User.student_offerings, course)
                              | User.attendances.any(Attendance.course == course))
            .options(joinedload(User.attendances).joinedload(Attendance.session))
            .all()
        ):
            emails.add(user.email)
            for attendance in [a for a in user.attendances if a.course == course]:
                try:
                    section_name = attendance.session.section.name
                except AttributeError:
                    section_name = "Session not associated with a section"
                if section_name not in attendances:
                    attendances[section_name] = {}
                if user.email not in attendances[section_name]:
                    attendances[section_name][user.email] = []
                attendances[section_name][user.email].append(
                    {
                        "section_id": attendance.session.section_id,
                        "start_time": attendance.session.start_time,
                        "status": attendance.status.name,
                    }
                )
        for email in emails:
            for attendance in attendances.values():
                if email not in attendance:
                    attendance[email] = []

        return {
            **refresh_state(),
            "custom": {
                "fileName": "attendances.json",
                "attendances": stringify(
                    [{"type": k, "attendances": v} for k, v in attendances.items()]
                ),
            },
        }

    def api_keys_json():
        keys = ApiKey.query.filter_by(course=get_course(), revoked_at=None).order_by(ApiKey.created_at)
        return [api_key.json for api_key in keys]

    def find_api_key(key_id) -> ApiKey:
        api_key = ApiKey.query.filter_by(id=int(key_id), course=get_course(), revoked_at=None).one_or_none()
        if api_key is None:
            raise Failure("That API key doesn't exist or was already revoked.")
        return api_key

    @api
    @admin_required
    @session_only
    def list_api_keys():
        return api_keys_json()

    @api
    @admin_required
    @session_only
    def create_api_key(name: str):
        name = name.strip() if isinstance(name, str) else ""
        if not name:
            raise Failure("Give the key a name, e.g. what it's for.")
        check_fits("The key's name", name, ApiKey.name)
        _, key = create_key(current_user, name)
        db.session.commit()
        return {"key": key, "name": name, "keys": api_keys_json()}

    @api
    @admin_required
    @session_only
    def revoke_api_key(key_id: str):
        # Any admin may revoke any key in the course, e.g. a departed TA's.
        api_key = find_api_key(key_id)
        api_key.revoked_at = int(time.time())
        db.session.commit()
        audit_log.info("key %d (%r, owner %s) in %s revoked by %s", api_key.id, api_key.name,
                       api_key.owner.email, api_key.course, current_user.email)
        return api_keys_json()

    @api
    @admin_required
    @session_only
    def rotate_api_key(key_id: str):
        """Replace one of your keys with a new one with the same name."""
        old = find_api_key(key_id)
        if old.owner_id != current_user.id:
            raise Failure("You can only rotate your own API keys. Revoke this one instead.")
        old.revoked_at = int(time.time())
        new, key = create_key(current_user, old.name)
        db.session.commit()
        audit_log.info("key %d (%r, owner %s) in %s rotated to key %d", old.id, old.name,
                       current_user.email, old.course, new.id)
        return {"key": key, "name": new.name, "keys": api_keys_json()}

    @api
    @admin_required
    def export_rosters():
        # Produce CSV based on Import Enrollment Form Style:
        # Column titles are Student Email, Staff Email, Location, Day, Start, Type
        out = StringIO()
        writer = csv.writer(out)
        writer.writerow(["Student Email", "Staff Email", "Location", "Day", "Start", "Type"])

        for section in Section.query.filter_by(course=get_course()).all():
            staff_email = section.staff.email if section.staff else ""
            location = section.location or ""
            day = ""
            start = ""

            DAY_MAP = {
                0: "M",
                1: "T",
                2: "W",
                3: "Th",
                4: "F",
            }

            try:

                if isinstance(section.start_time, (int, float)):
                    # Interpret stored UNIX timestamps in America/LA timezones
                    tz = ZoneInfo("America/Los_Angeles")
                    dt = datetime.fromtimestamp(section.start_time, tz=tz)
                    day = DAY_MAP.get(dt.weekday(), "")  # e.g. "M", "Tu"
                    start = dt.strftime("%I:%M%p").lower().replace('m', '')  # e.g. "08:00a"
                else:
                    # fallback: output as-is (just as a string)
                    start = str(section.start_time or "")
            except Exception:
                day = ""
                start = str(section.start_time or "")

            for student in section.students:
                writer.writerow([student.email, staff_email, location, day, start, section.name or ""])

        csv_text = out.getvalue()
        return {
            **refresh_state(),
            "custom": {"fileName": "rosters.csv", "rosters": csv_text},
        }

    @api
    @staff_required
    def fetch_user(user_id: str):
        user_id = int(user_id)
        user = offering_member(id=user_id)
        if user is None:
            raise Failure(f"No user found with id {user_id}")
        return user.simple_json

    @api
    @staff_required
    def get_userid(email: str):
        user = offering_member(email=email)
        if user is None:
            raise Failure(f"No user found with email {email}")
        return user.id

    @api
    @admin_required
    def import_sections_from_sheet(url: str):
        added, updated = import_sections_from_url(url)
        return {
            **refresh_state(),
            "custom": {"message": f"Added {added} sections and updated {updated} existing ones."},
        }

    @api
    @admin_required
    def import_enrollment_from_sheet(url: str):
        import_enrollment_from_url(url)
        return refresh_state()

    @api
    @admin_required
    def reset_sections():
        course = get_course()
        for section in Section.query.filter_by(course=course).all():
            section.staff = None
        Attendance.query.filter_by(course=course).delete()
        Session.query.filter_by(course=course).delete()

        # Remove the offering's sections and everyone's assignments to them, but
        # keep the people and their roles in the offering.
        course_section_ids = [s.id for s in Section.query.filter_by(course=course)]
        db.session.execute(
            user_section.delete().where(user_section.c.section_id.in_(course_section_ids))
        )
        Section.query.filter_by(course=course).delete()
        db.session.commit()
        return refresh_state()

    @api
    @admin_required
    def fetch_to_drop():
        students = ""
        course = get_course()
        for student in (
            User.query.filter(set_contains(User.student_offerings, course))
            .filter(User.sections.any(Section.course == course))
            .all()
        ):
            tutoring_section = None
            absences = []
            excused = []
            if student:
                for section in student.sections_in(course):
                    if section.name == 'Tutoring':
                        tutoring_section = section
            if tutoring_section:
                excused = (Attendance.query.join(Attendance.session)
                .filter(
                    Attendance.student_id == student.id,
                    Attendance.status == AttendanceStatus.excused,
                    Session.section_id == tutoring_section.id
                )
                .options(joinedload(Attendance.session))
                .all()
                )
            if tutoring_section:
                absences = (Attendance.query.join(Attendance.session)
                .filter(
                    Attendance.student_id == student.id,
                    Attendance.status == AttendanceStatus.absent,
                    Session.section_id == tutoring_section.id
                )
                .options(joinedload(Attendance.session))
                .all()
                )
            if (len(absences) >= 1 or len(excused) >= 3):
                students += student.email + ", "
        return {
            **refresh_state(),
            "custom": {"students": students[:-2]},
        }

    @api
    @admin_required
    def get_student_section_ids(email: str):
        student = offering_member(email=email)
        if (student is None):
            return {email: []}
        section_ids = [section.id for section in student.sections_in(get_course())]
        return {email: section_ids}

    @api
    @admin_required
    def get_student_discussion_attendance(email:str):
        student = offering_member(email=email)
        discussion_present_days = []
        if student:
            attendances = (Attendance.query.join(Attendance.session).join(Session.section)
            .filter(
                Attendance.student_id == student.id,
                Attendance.status == AttendanceStatus.present,
                Section.name == 'Discussion',
                Section.course == get_course()
            )
            .options(joinedload(Attendance.session))
            .all()
            )
            discussion_present_days = [attendance.session.start_time for attendance in attendances]
        return {"attendance": discussion_present_days}


    @api
    @admin_required
    def get_student_lab_attendance(email:str):
        student = offering_member(email=email)
        lab_present_days = []
        if student:
            attendances = (Attendance.query.join(Attendance.session).join(Session.section)
            .filter(
                Attendance.student_id == student.id,
                Attendance.status == AttendanceStatus.present,
                Section.name == 'Lab',
                Section.course == get_course()
            )
            .options(joinedload(Attendance.session))
            .all()
            )
            lab_present_days = [attendance.session.start_time for attendance in attendances]
        return {"attendance": lab_present_days}

    @api
    @admin_required
    def get_student_tutoring_attendance(email:str):
        student = offering_member(email=email)
        tutoring_present_days = []
        if student:
            attendances = (Attendance.query.join(Attendance.session).join(Session.section)
            .filter(
                Attendance.student_id == student.id,
                Attendance.status == AttendanceStatus.present,
                Section.name == 'Tutoring',
                Section.course == get_course()
            )
            .options(joinedload(Attendance.session))
            .all()
            )
            tutoring_present_days = [attendance.session.start_time for attendance in attendances]
        return {"attendance": tutoring_present_days}

    app.register_blueprint(bp)
