from enum import Enum
from random import randrange
from typing import List
from urllib.parse import quote

from flask import g
from flask_login import UserMixin, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import literal, types
from sqlalchemy.orm import DeclarativeBase, joinedload


class Base(DeclarativeBase):
    # The models use plain type hints rather than SQLAlchemy 2.0's Mapped[] annotations.
    __allow_unmapped__ = True


db = SQLAlchemy(model_class=Base)


class StringSet(types.TypeDecorator):
    """A set of strings stored as comma-separated text, as in seating."""

    impl = types.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return ",".join(sorted(set(value or ())))

    def process_result_value(self, value, dialect):
        return set(value.split(",")) if value else set()


def set_contains(column, item: str):
    """SQL condition: the StringSet ``column`` contains ``item``."""
    return (literal(",") + db.func.coalesce(column, "") + literal(",")).like(f"%,{item},%")


def current_course_key():
    """The current offering's key, or None outside an offering's pages."""
    return g.offering.key if "offering" in g else None

# Association Table for User - Section Pairs because each user can have multiple sections
user_section = db.Table('user_section',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('section_id', db.Integer, db.ForeignKey('section.id'), primary_key=True)
)


class Section(db.Model):
    id: int = db.Column(db.Integer, primary_key=True)
    course: str = db.Column(db.String(255), index=True)
    description: str = db.Column(db.String(255))
    capacity: int = db.Column(db.Integer)
    can_self_enroll: bool = db.Column(db.Boolean)
    enrollment_code: str = db.Column(db.String(255), nullable=True)
    staff_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
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
    student_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
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
    """One person, across all offerings, like seating's User.

    Roles are per offering, in sets of offering keys (the value of each row's
    `course` column) rather than seating's Canvas IDs, because offerings moved
    from the monorepo aren't all linked to Canvas. Inside an offering's pages,
    `is_staff` and `is_admin` answer for that offering.
    """

    __tablename__ = "users"
    id: int = db.Column(db.Integer, primary_key=True)
    email: str = db.Column(db.String(255), unique=True, index=True, nullable=False)
    name: str = db.Column(db.String(255), nullable=False)
    # Set when the person first logs in; people added by staff or imported from
    # a spreadsheet may not have one.
    canvas_id: str = db.Column(db.String(255), unique=True, index=True, nullable=True)
    # Staff and admin in every offering (member of ADMIN_OVERRIDE_CANVAS_COURSE_ID).
    is_global_admin: bool = db.Column(db.Boolean, nullable=False, default=False)
    # Active Canvas courses at last login, keyed by str(canvas course id):
    # {"name", "code", "start_at", "is_staff", "is_admin", "is_student"}.
    canvas_courses: dict = db.Column(db.JSON, nullable=False, default=dict)
    staff_offerings: set = db.Column(StringSet, nullable=False, default=set)
    admin_offerings: set = db.Column(StringSet, nullable=False, default=set)
    student_offerings: set = db.Column(StringSet, nullable=False, default=set)

    sections: List["Section"] = db.relationship(
        'Section', secondary=user_section, back_populates='students', lazy='joined'
    )
    # attendances: List[Attendance] is a backref defined on Attendance

    def __init__(self, **kwargs):
        # Column defaults only apply on insert; set_role needs real sets before then.
        for field in ("staff_offerings", "admin_offerings", "student_offerings"):
            kwargs.setdefault(field, set())
        kwargs.setdefault("canvas_courses", {})
        kwargs.setdefault("is_global_admin", False)
        super().__init__(**kwargs)

    # Session ids are prefixed so cookies from before this table existed, which
    # hold the id of a different table's row, can't be mistaken for a user id.
    SESSION_ID_PREFIX = "user-"

    def get_id(self):
        return f"{self.SESSION_ID_PREFIX}{self.id}"

    @classmethod
    def parse_session_id(cls, session_id: str):
        prefix, _, user_id = session_id.partition(cls.SESSION_ID_PREFIX)
        return int(user_id) if not prefix and user_id.isdigit() else None

    @property
    def is_staff(self) -> bool:
        key = current_course_key()
        return key is not None and (self.is_global_admin or key in self.staff_offerings)

    @property
    def is_admin(self) -> bool:
        key = current_course_key()
        return key is not None and (self.is_global_admin or key in self.admin_offerings)

    def is_member_of(self, key: str) -> bool:
        return key in self.staff_offerings or key in self.student_offerings

    def set_role(self, key: str, *, is_staff: bool, is_admin: bool = False):
        """Make this person staff (optionally admin) or a student in an offering."""
        if is_staff:
            self.staff_offerings = self.staff_offerings | {key}
            self.student_offerings = self.student_offerings - {key}
        else:
            self.student_offerings = self.student_offerings | {key}
            self.staff_offerings = self.staff_offerings - {key}
        if is_admin:
            self.admin_offerings = self.admin_offerings | {key}
        else:
            self.admin_offerings = self.admin_offerings - {key}

    def sections_in(self, key: str) -> List["Section"]:
        return [section for section in self.sections if section.course == key]

    def canvas_roles_in(self, canvas_course_id: int):
        """``(is_staff, is_admin)`` in a Canvas course from the last login, or
        None if not enrolled there."""
        info = (self.canvas_courses or {}).get(str(canvas_course_id))
        if info is None or not (info["is_staff"] or info["is_student"]):
            return None
        return info["is_staff"], info["is_admin"]

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
            Attendance.query.filter_by(student_id=self.id, course=current_course_key())
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
            Attendance.query.filter_by(student_id=self.id, course=current_course_key())
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


def offering_member(**filters):
    """The person matching ``filters`` (e.g. email=...) if they're in the
    current offering, otherwise None."""
    user = User.query.filter_by(**filters).one_or_none()
    return user if user is not None and user.is_member_of(current_course_key()) else None


def find_or_add_person(email: str, name: str) -> User:
    """The person with this email, created (not yet in any offering) if new."""
    user = User.query.filter_by(email=email).one_or_none()
    if user is None:
        user = User(email=email, name=name)
        db.session.add(user)
    return user


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


class Offering(db.Model):
    """One semester's bCourses course that has been set up in this app, like
    seating's Offering."""

    __tablename__ = "offerings"
    id: int = db.Column(db.Integer, primary_key=True)
    canvas_id: int = db.Column(db.Integer, unique=True, index=True, nullable=False)
    # The value of the `course` column on every other table. Offerings set up in
    # this app use str(canvas_id); offerings moved from the monorepo keep their
    # old key (e.g. "cs61a") so their existing rows don't need rewriting.
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

    def __str__(self):
        return f"{self.start_month} | {self.code} | {self.name}"

    def __repr__(self):
        return f"<Offering {self.name}>"


class Failure(Exception):
    pass
