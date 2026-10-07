from enum import Enum
from random import randrange
from typing import List
from urllib.parse import quote

from flask_login import UserMixin, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, joinedload


class Base(DeclarativeBase):
    # The models use plain type hints rather than SQLAlchemy 2.0's Mapped[] annotations.
    __allow_unmapped__ = True


db = SQLAlchemy(model_class=Base)

# Association Table for User - Section Pairs because each user can have multiple sections
user_section = db.Table('user_section',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('section_id', db.Integer, db.ForeignKey('section.id'), primary_key=True)
)


class Section(db.Model):
    id: int = db.Column(db.Integer, primary_key=True)
    course: str = db.Column(db.String(255), index=True)
    description: str = db.Column(db.String(255))
    capacity: int = db.Column(db.Integer)
    can_self_enroll: bool = db.Column(db.Boolean)
    enrollment_code: str = db.Column(db.String(255), nullable=True)
    staff_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    staff: "User" = db.relationship(
        "User",
        backref=db.backref("sections_taught", lazy="joined"),
        lazy="joined",
        foreign_keys=[staff_id],
    )
    tag_string: str = db.Column(
        db.String(255), nullable=False, default=""
    )  # comma separated list of tags
    students: List["User"] = db.relationship('User', secondary=user_section, back_populates='sections', lazy='joined')
    # moved attributes from slots to section for decoupling
    name: str = db.Column(db.String(255)) # indicates section type e.g. lab or discussion
    start_time: int = db.Column(db.Integer)
    end_time: int = db.Column(db.Integer)
    location: str = db.Column(db.String(255), nullable=False)
    call_link: str = db.Column(db.String(255), nullable=True)
    # sessions: List[Session] is a backref defined on Session

    @property
    def tags(self):
        return self.tag_string.split(",")

    @tags.setter
    def tags(self, tags: List[str]):
        self.tag_string = ",".join(tags)

    @property
    def needs_enrollment_code(self):
        return self.enrollment_code not in ["", None]

    @property
    def json(self):
        return self.to_json()

    def to_json(
        self,
        include_students=True,
        enrollment_count=None,
        reveal_roster=False,
    ):
        if include_students:
            students = [
                student.identity_json if reveal_roster else student.json
                for student in sorted(self.students, key=lambda student: student.name)
            ]
            if enrollment_count is None:
                enrollment_count = len(students)
        else:
            if enrollment_count is None:
                raise ValueError("enrollment_count is required without a roster")
            # Clients loaded before this API change still use students.length for
            # capacity. Preserve that behavior without exposing or serializing the
            # course-wide roster. New clients use enrollmentCount directly.
            students = [None] * enrollment_count

        return {
            "id": str(self.id),
            "staff": self.staff.json if self.staff is not None else None,
            "students": students,
            "enrollmentCount": enrollment_count,
            "description": self.description,
            "capacity": self.capacity,
            "canSelfEnroll": self.can_self_enroll,
            "needsEnrollmentCode": self.needs_enrollment_code,
            "tags": self.tags,
            "enrollmentCode": self.enrollment_code if current_user.is_staff else None,

            # transfered attributes from slots for decoupling
            "name": self.name,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "location": self.location,
            "callLink": self.call_link,
        }

    @property
    def full_json(self):
        return {
            **self.json,
            "sessions": [
                session.full_json
                for session in sorted(
                    self.sessions, key=lambda session: session.start_time
                )
            ],
        }


class Session(db.Model):
    id: int = db.Column(db.Integer, primary_key=True)
    course: str = db.Column(db.String(255), index=True)
    start_time: int = db.Column(db.Integer)
    section_id: int = db.Column(db.Integer, db.ForeignKey("section.id"), index=True)
    section: Section = db.relationship(lambda: Section, backref=db.backref("sessions"), lazy="joined")
    # attendances: List[Attendance] is a backref defined on Attendance

    @property
    def json(self):
        return {"id": self.id, "startTime": self.start_time}

    @property
    def full_json(self):
        return {
            **self.json,
            "attendances": [
                attendance.json
                for attendance in sorted(
                    self.attendances, key=lambda attendance: attendance.student.name
                )
            ],
        }


# note that the *keys* are persisted to the db, not the values
class AttendanceStatus(Enum):
    present = 1
    excused = 2
    absent = 3


class Attendance(db.Model):
    id: int = db.Column(db.Integer, primary_key=True)
    course: str = db.Column(db.String(255), index=True)
    status: AttendanceStatus = db.Column(db.Enum(AttendanceStatus, name="attendance_status"))
    session_id: int = db.Column(db.Integer, db.ForeignKey("session.id"), index=True)
    session: Session = db.relationship(
        lambda: Session,
        backref=db.backref("attendances", lazy="joined"),
        lazy="joined",
        innerjoin=True,
    )
    student_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    student: "User" = db.relationship(
       lambda: User, backref=db.backref("attendances"), lazy="joined", innerjoin=True
    )

    @property
    def json(self):
        if not current_user.is_staff and self.student_id != current_user.id:
            raise Failure("Attendance data of other users is staff-only")
        return {"student": self.student.json, "status": self.status.name}

    @property
    def full_json(self):
        return {
            **self.json,
            "session": self.session.json,
            "section": self.session.section.json if self.session.section else None
        }


class User(db.Model, UserMixin):
    # just here to make PyCharm stop complaining
    def __init__(self, email: str, name: str, is_staff: bool, course: str, is_admin: bool):
        # noinspection PyArgumentList
        super().__init__(email=email, name=name, is_staff=is_staff, course=course, is_admin=is_admin)
    id: int = db.Column(db.Integer, primary_key=True)
    course: str = db.Column(db.String(255), index=True)
    email: str = db.Column(db.String(255), index=True)
    name: str = db.Column(db.String(255))
    is_staff: bool = db.Column(db.Boolean)
    is_admin: bool = db.Column(db.Boolean)

    sections: List["Section"] = db.relationship(
        'Section', secondary=user_section, back_populates='students', lazy='joined'
    )
    # attendances: List[Attendance] is a backref defined on Attendance

    @property
    def identity_json(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "isStaff": self.is_staff,
            "isAdmin": self.is_admin,
        }

    @property
    def json(self):
        can_see = (
            current_user.is_staff
            or self.is_staff
            or self.id == current_user.id
            or any([s in self.sections for s in current_user.sections])
        )
        if can_see:
            return self.identity_json
        else:
            return {
                "id": randrange(10**6),
                "name": "Anon Student",
                "email": "",
                "isStaff": False,
                "isAdmin": False,
            }

    @property
    def full_json(self):
        attendances = (
            Attendance.query.filter_by(student_id=self.id)
            .options(
                joinedload(Attendance.session, innerjoin=True)
                .joinedload(Session.section)
                .joinedload(Section.staff)
            )
            .all()
        )
        return {
            **self.json,
            "isAdmin": self.is_admin,
            "attendanceHistory": [
                attendance.full_json
                for attendance in sorted(
                    attendances, key=lambda attendance: attendance.session.start_time
                )
            ],
        }

    @property
    def simple_json(self):
        attendances = (
            Attendance.query.filter_by(student_id=self.id)
            .options(
                joinedload(Attendance.session, innerjoin=True)
                .joinedload(Session.section)
                .joinedload(Section.staff)
            )
            .all()
        )
        return {
            **self.json,
            "isAdmin": self.is_admin,
            "attendanceHistory": [
                {
                    "status": attendance.status.name,
                    "session": {
                        "id": attendance.session.id,
                        "startTime": attendance.session.start_time,
                    },
                    "section": {
                        "id": attendance.session.section.id,
                        "name": attendance.session.section.name,
                        "location": attendance.session.section.location,
                        "staff": attendance.session.section.staff.json
                            if attendance.session.section.staff is not None
                            else None,
                    } if attendance.session.section else None,
                }
                for attendance in sorted(
                    attendances, key=lambda attendance: attendance.session.start_time
                )
            ],
        }


class CourseConfig(db.Model):
    id: int = db.Column(db.Integer, primary_key=True)
    course: str = db.Column(db.String(255), index=True)

    can_students_join_lab =  db.Column(db.Boolean, default=True)
    can_students_change_lab = db.Column(db.Boolean, default=True)
    can_tutors_change_lab = db.Column(db.Boolean, default=True)
    can_tutors_reassign_lab = db.Column(db.Boolean, default=True)
    can_students_join_disc = db.Column(db.Boolean, default=True)
    can_students_change_disc = db.Column(db.Boolean, default=True)
    can_tutors_change_disc = db.Column(db.Boolean, default=True)
    can_tutors_reassign_disc = db.Column(db.Boolean, default=True)
    can_students_join_tutoring = db.Column(db.Boolean, default=True)
    can_students_change_tutoring = db.Column(db.Boolean, default=True)
    can_tutors_change_tutoring = db.Column(db.Boolean, default=True)
    can_tutors_reassign_tutoring = db.Column(db.Boolean, default=True)

    message: str = db.Column(db.String(1024), default="")

    @property
    def json(self):
        return {
            "canStudentsJoinLab": self.can_students_join_lab,
            "canStudentsChangeLab": self.can_students_change_lab,
            "canTutorsChangeLab": self.can_tutors_change_lab,
            "canTutorsReassignLab": self.can_tutors_reassign_lab,
            "canStudentsJoinDiscussion": self.can_students_join_disc,
            "canStudentsChangeDiscussion": self.can_students_change_disc,
            "canTutorsChangeDiscussion": self.can_tutors_change_disc,
            "canTutorsReassignDiscussion": self.can_tutors_reassign_disc,
            "canStudentsJoinTutoring": self.can_students_join_tutoring,
            "canStudentsChangeTutoring": self.can_students_change_tutoring,
            "canTutorsChangeTutoring": self.can_tutors_change_tutoring,
            "canTutorsReassignTutoring": self.can_tutors_reassign_tutoring,
            "message": self.message,
        }


class Course(db.Model):
    """A bCourses course that has been set up in this app."""

    id: int = db.Column(db.Integer, primary_key=True)
    canvas_id: int = db.Column(db.Integer, unique=True, index=True, nullable=False)
    # The value of the `course` column on every other table. Courses set up in
    # this app use str(canvas_id); courses moved from the monorepo keep their old
    # key (e.g. "cs61a") so their existing rows don't need rewriting.
    key: str = db.Column(db.String(255), unique=True, nullable=False)
    # Canvas course name (e.g. "COMPSCI 61A - LEC 001") and code (e.g. "COMPSCI 61A").
    name: str = db.Column(db.String(255), nullable=False)
    code: str = db.Column(db.String(255), nullable=True)
    # ISO 8601 start of the course's term, as in seating.
    start_at: str = db.Column(db.String(255), nullable=True)

    @property
    def display_name(self) -> str:
        return self.code or self.name

    @property
    def start_month(self) -> str:
        return (self.start_at or "")[:7]


class Account(db.Model, UserMixin):
    """Someone signed in with Canvas, across all of their courses.

    Flask-Login keeps the account's id in the session. Inside a course, the
    login manager resolves it to that course's User row (see login.py).
    """

    id: int = db.Column(db.Integer, primary_key=True)
    canvas_id: str = db.Column(db.String(255), unique=True, index=True, nullable=False)
    email: str = db.Column(db.String(255), index=True, nullable=False)
    name: str = db.Column(db.String(255), nullable=False)
    # Staff and admin in every course (member of ADMIN_OVERRIDE_CANVAS_COURSE_ID).
    is_global_admin: bool = db.Column(db.Boolean, nullable=False, default=False)
    # Active Canvas courses at last sign-in, keyed by str(canvas course id):
    # {"name", "code", "start_at", "is_staff", "is_admin", "is_student"}.
    canvas_courses: dict = db.Column(db.JSON, nullable=False, default=dict)

    # Session ids are prefixed so cookies from before accounts existed, which
    # hold a per-course User id, can't be mistaken for an account id.
    SESSION_ID_PREFIX = "account-"

    def get_id(self):
        return f"{self.SESSION_ID_PREFIX}{self.id}"

    @classmethod
    def parse_session_id(cls, session_id: str):
        prefix, _, account_id = session_id.partition(cls.SESSION_ID_PREFIX)
        return int(account_id) if not prefix and account_id.isdigit() else None

    def roles_in(self, canvas_course_id: int):
        """``(is_staff, is_admin)`` in the course, or None if not enrolled."""
        if self.is_global_admin:
            return True, True
        info = self.canvas_courses.get(str(canvas_course_id))
        if info is None or not (info["is_staff"] or info["is_student"]):
            return None
        return info["is_staff"], info["is_admin"]


class Failure(Exception):
    pass
