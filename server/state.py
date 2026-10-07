import csv
import hmac
import re
import time
from canvasapi.exceptions import InvalidAccessToken, Unauthorized

from io import StringIO
from datetime import datetime
from functools import wraps
from json import dumps
from typing import List, Optional, Union
from zoneinfo import ZoneInfo
from import_sheet import parse_time_string

import flask
from flask import abort, jsonify, render_template, request, current_app, session
from flask_login import current_user, login_required, login_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload, noload

import canvas_service
from course import format_coursecode, get_course
from import_sheet import import_sections_from_url, import_enrollment_from_url
from slack import post_slack_message

from models import (
    Attendance,
    AttendanceStatus,
    CourseConfig,
    Failure,
    Section,
    Session,
    User,
    db,
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


def admin_required(func):
    @wraps(func)
    @staff_required
    def wrapped(**kwargs):
        if not current_user.is_admin:
            raise Failure("Only course admins can perform this action.")
        return func(**kwargs)

    return wrapped


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

def is_valid_api_secret(secret) -> bool:
    expected = current_app.config.get("API_SECRET")
    return bool(expected) and isinstance(secret, str) and hmac.compare_digest(secret, expected)


def add_student_helper(student: User, target_section: Section):
    if len(set([s.name for s in student.sections])) != len(student.sections):
        raise Failure("Student has multiple sections of the same type")

    # If user is already in a section of the same type, remove it and add target section
    for s in student.sections:
        if s.name == target_section.name:
            student.sections.remove(s)
            break
    student.sections.append(target_section)
    # SQLAlchemy 2.0 no longer cascades new objects into the session through backrefs.
    db.session.add(student)

def create_state_client(app: flask.Flask):
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

        app.add_url_rule(
            f"/api/{handler.__name__}", handler.__name__, wrapped, methods=["POST"]
        )

        def sudo_wrapped():
            data = request.json
            secret = data["secret"]
            email = data["email"]
            args = data["args"]

            if not is_valid_api_secret(secret):
                abort(401)

            user = User.query.filter_by(course=get_course(), email=email).one()
            login_user(user)
            try:
                return jsonify({"success": True, "data": handler(**args)})
            except Failure as failure:
                return jsonify({"success": False, "message": str(failure)})

        app.add_url_rule(
            f"/api/sudo/{handler.__name__}",
            "sudo_" + handler.__name__,
            sudo_wrapped,
            methods=["POST"],
        )

        return handler

    @app.route("/", endpoint="index")
    @app.route("/history/")
    @app.route("/lab/")
    @app.route("/disc/")
    @app.route("/tutoring/")
    @app.route("/admin/")
    @app.route("/section/<path:path>")
    @app.route("/user/<path:path>")
    def generic(**_):
        return render_template("index.html", course=format_coursecode(get_course()))

    @app.route("/debug")
    def debug():
        refresh_state()
        return "<body></body>"

    @api
    def refresh_state():
        """
        Returns overall information about the section in json.

        Backend API functions calling refresh_state should be called
        using the useAPI hook in frontend.
        """
        refresh_started_at = time.perf_counter()
        config = CourseConfig.query.filter_by(course=get_course()).one_or_none()
        if config is None:
            config = CourseConfig(course=get_course())
            db.session.add(config)
            db.session.commit()

        out = {
            "enrolledSections": None,
            "taughtSections": None,
            "sections": [],
            "currentUser": None,
            "course": format_coursecode(get_course()),
            "config": config.json,
            "custom": None,
        }

        if current_user.is_authenticated:
            course = get_course()
            enrolled_sections = list(current_user.sections)
            taught_sections = list(current_user.sections_taught)
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
            if any(current_user.sections):
                raise Failure("Students cannot change their enrolled discussion!")
            else:
                raise Failure("Students cannot add themselves themselves to discussions!")
        if target_section.name == "Lab" and not config.can_students_join_lab:
            if any(current_user.sections):
                raise Failure("Students cannot change their enrolled lab!")
            else:
                raise Failure("Students cannot add themselves themselves to labs!")
        if target_section.name == "Tutoring" and not config.can_students_join_tutoring:
            if any(current_user.sections):
                raise Failure("Students cannot change their enrolled tutorial!")
            else:
                raise Failure("Students cannot add themselves themselves to tutorials!")

        # If student is already enrolled in a section of the same type/name (Lab/Disc/etc)
        if any(map(lambda section: section.name == target_section.name, current_user.sections)):
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
        if not all(can_change.get(s.name, True) for s in current_user.sections):
            raise Failure("Students cannot remove themselves from sections!")

        current_user.sections = []

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
        section.description = description
        db.session.commit()
        return refresh_state()

    @api
    @staff_required
    def update_section_call_link(section_id: str, call_link: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        section.call_link = call_link
        db.session.commit()
        return refresh_state()

    @api
    @staff_required
    def update_section_enrollment_code(section_id: str, enrollment_code: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        section.enrollment_code = enrollment_code
        db.session.commit()
        return refresh_state()

    @api
    @admin_required
    def update_section_location(section_id: str, new_location: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        section.location = new_location
        db.session.commit()
        return fetch_section(section_id=section_id)

    @api
    @admin_required
    def update_section_time(section_id: str, day: str, start_time: str, end_time: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        section.start_time = parse_time_string(day, start_time)
        section.end_time = parse_time_string(day, end_time)
        db.session.commit()
        return fetch_section(section_id=section_id)

    @api
    @admin_required
    def update_section_tags(section_id: str, tags: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        section.tags = tags.split(",")
        db.session.commit()
        return fetch_section(section_id=section_id)

    @api
    @staff_required
    def start_session(section_id: str, start_time: int):
        section_id = int(section_id)
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
        status = AttendanceStatus[status]
        for email in parse_emails(students):
            student = User.query.filter_by(
                email=email, course=get_course()
            ).one_or_none()
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
        for key, value in kwargs.items():
            setattr(config, key, value)
        db.session.commit()
        return refresh_state()

    @api
    @staff_required
    def remove_student(student: str, section_id: str):
        section_id = int(section_id)
        student = User.query.filter_by(email=student, course=get_course()).one()
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        student.sections.remove(section)
        db.session.commit()
        return fetch_section(section_id=section_id)

    @api
    @admin_required
    def remove_students(students: str):
        for s in parse_emails(students):
            student = User.query.filter_by(email=s, course=get_course()).one_or_none()
            if student:
                student.sections = []
        db.session.commit()
        return refresh_state()

    @api
    @admin_required
    def remove_students_from_tutoring(students: str):
        for s in parse_emails(students):
            student = User.query.filter_by(email=s, course=get_course()).one_or_none()
            if student:
                student.sections = [sec for sec in student.sections if sec.name != "Tutoring"]
        db.session.commit()
        return refresh_state()

    @api
    @staff_required
    def add_student(email: str, section_id: str):
        #this function is never called!! use add_students instead
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        student = User.query.filter_by(email=email, course=get_course()).one_or_none()
        if student is None:
            student = User(email=email, name=email, is_staff=False, is_admin=False, course=get_course())

        # for decoupling
        add_student_helper(student, section)
        db.session.commit()

        return fetch_section(section_id=section_id)

    @api
    @staff_required
    def add_students(emails: str, section_id: str):
        section_id = int(section_id)
        section = Section.query.filter_by(id=section_id, course=get_course()).one()
        access_token = session.get("canvas_access_token")
        for email in parse_emails(emails):
            student = User.query.filter_by(
                email=email, course=get_course()
            ).one_or_none()
            if student is not None and student.is_staff:
                raise Failure("Attempted to add staff: {student.name}")
            if student is None:
                # Existing students need no Canvas token; unknown students need a fresh login.
                if not access_token or time.time() + 60 >= session.get("canvas_token_expires_at", 0):
                    raise Failure(
                        "Canvas authorization has expired. Please log out and sign in "
                        "with Canvas again, then retry adding students."
                    )
                try:
                    canvasname = canvas_service.get_student_from_email(
                        email, access_token
                    )
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

                if (not canvasname):
                    raise Failure("Could not find email that belongs to this class")
                student = User(
                    email=email, name=canvasname, is_staff=False, is_admin=False, course=get_course()
                )
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

    @api
    def export_attendance_secret(secret: str):
        if is_valid_api_secret(secret):
            return export_helper()
        raise Failure("Invalid secret")

    def export_helper():
        stringify = dumps
        attendances = dict()
        emails = set()
        for user in (
            User.query.filter_by(is_staff=False, course=get_course())
            .options(joinedload(User.attendances).joinedload(Attendance.session))
            .all()
        ):
            emails.add(user.email)
            for attendance in user.attendances:
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
        user = User.query.filter_by(id=user_id, course=get_course()).one_or_none()
        if user is None:
            raise Failure(f"No user found with id {user_id}")
        return user.simple_json

    @api
    @staff_required
    def get_userid(email: str):
        user = User.query.filter_by(email=email, course=get_course()).one_or_none()
        if user is None:
            raise Failure(f"No user found with email {email}")
        return user.id

    @api
    @admin_required
    def remind_tutors_to_setup_zoom_links():
        sections: List[Section] = Section.query.filter_by(
            call_link=None, course=get_course()
        ).all()
        tutor_emails = set()
        for section in sections:
            tutor_emails.add(section.staff.email)
        tutor_emails = sorted(tutor_emails)
        if not tutor_emails:
            raise Failure("All tutors have set up their Zoom links!")

        message = (
            "The following tutors have not yet set up their Zoom links for all their sections:\n"
            + "\n".join(f" • {email}" for email in tutor_emails)
            + "\n Please do so ASAP! Thanks."
        )

        post_slack_message(message)

        return refresh_state()

    @api
    @admin_required
    def import_sections_from_sheet(url: str):
        import_sections_from_url(url)
        return refresh_state()

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

        for user in User.query.filter_by(course=course).all():
            user.sections.clear()

        User.query.filter_by(course=course).delete()
        Section.query.filter_by(course=course).delete()
        db.session.commit()
        return refresh_state()

    @api
    @admin_required
    def fetch_to_drop():
        students = ""
        for student in (
            User.query.filter_by(is_staff=False, course=get_course())
            .filter(User.sections.any())
            .all()
        ):
            tutoring_section = None
            absences = []
            excused = []
            if student:
                for section in student.sections:
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
        student = User.query.filter_by(
            email= email,
            course=get_course()
        ).one_or_none()
        if (student is None):
            return {email: []}
        section_ids = [section.id for section in student.sections]
        return {email: section_ids}

    @api
    @admin_required
    def get_student_discussion_attendance(email:str):
        student = User.query.filter_by(
                    email = email,
                    course=get_course()
                ).one_or_none()
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
        student = User.query.filter_by(
                    email = email,
                    course=get_course()
                ).one_or_none()
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
        student = User.query.filter_by(
                    email = email,
                    course=get_course()
                ).one_or_none()
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
