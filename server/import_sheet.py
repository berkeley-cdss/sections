from __future__ import annotations

from datetime import datetime
from typing import List, Iterator

from zoneinfo import ZoneInfo

from offering import get_course
from google_sheets import read_spreadsheet
from dataclasses import asdict, dataclass, field, fields
from models import Failure, Section, db, find_or_add_person, offering_member, user_section

# Sample Spreadsheet Link: https://docs.google.com/spreadsheets/d/1WL7gXiBxPe6aUFBKfEOVS6iY27ITy9mARupLoJX-ouE/edit?usp=sharing
pst = ZoneInfo("US/Pacific")


def parse_time_string(day, time):
    hour, min, ampm = int(time[0:2]), int(time[3:5]), time[5]

    day_offset = ["M", "T", "W", "Th", "F"].index(day)
    hour_offset = 12 if hour != 12 and ampm == "p" else 0

    return datetime(
        year=2021,
        month=8,
        day=23 + day_offset,
        hour=hour + hour_offset,
        minute=min,
        tzinfo=pst
    ).timestamp()


def header_field(col_name: str):
    return field(default=None, metadata=dict(col_name=col_name))


def try_assign(model, name, index):
    for f in fields(model):
        if "col_name" in f.metadata:
            if f.metadata["col_name"] == name:
                if getattr(model, f.name) is not None:
                    raise Failure(f"Duplicate attribute: {name}")
                setattr(model, f.name, index)
                return True
    return False

@dataclass
class SectionsHeader:
    email_index: int = header_field("Email")
    name_index: int = header_field("Name")
    capacity_index: int = header_field("Capacity")
    tags_index: int = header_field("Tags")
    self_enroll_index: int = header_field("Can Self Enroll")
    location_index: int = header_field("Location")
    day_index: int = header_field("Day")
    start_index: int = header_field("Start")
    end_index: int = header_field("End")
    type_index: int = header_field("Type")

@dataclass
class EnrollmentHeader:
    student_email_index: int = header_field("Student Email")
    student_name_index: int = header_field("Student Name")
    staff_email_index: int = header_field("Staff Email")
    location_index: int = header_field("Location")
    day_index: int = header_field("Day")
    start_index: int = header_field("Start")
    type_index: int = header_field("Type")


def process_header(model, header: List):
    for i, entry in enumerate(header):
        success = try_assign(model, entry, i)
        if not success:
            raise Failure(f"Unable to process column header '{entry}'")

    for attr, value in asdict(model).items():
        if value is None:
            raise Failure(f"Unable to find column corresponding to attribute '{attr}'")

    return model


def import_sections(data: Iterator):
    model = SectionsHeader()
    header = process_header(model, next(data))

    for row in data:
        email = row[header.email_index]
        name = row[header.name_index]
        capacity = row[header.capacity_index]
        tags = row[header.tags_index]
        can_self_enroll = row[header.self_enroll_index].lower()
        if can_self_enroll not in ("false", "true"):
            raise Failure(f"Unknown boolean value: {can_self_enroll}")
        can_self_enroll = can_self_enroll == "true"

        staff = offering_member(email=email)
        if staff is None:
            staff = find_or_add_person(email, name)
            staff.set_role(get_course(), is_staff=True)

        section_type = row[header.type_index]
        location = row[header.location_index]
        start_time = parse_time_string(
                    row[header.day_index], row[header.start_index])
        end_time=parse_time_string(row[header.day_index], row[header.end_index])

        section = Section(
            capacity=capacity,
            can_self_enroll=can_self_enroll,
            staff=staff,
            course=get_course(),
            name = section_type, # In models.py, name refers to the type of section (Lab/Discussion/Custom)
            start_time = start_time,
            end_time = end_time,
            location = location
        )

        section.tags = tags.split(",")

        db.session.add(section)

    db.session.commit()


def import_sections_from_url(url: str):
    try:
        reader = read_spreadsheet(
            url=url,
            sheet_name="Sections",
        )
    except Exception:
        raise Failure(
            "Unable to read spreadsheet. Make sure to put your data in a sheet named 'Sections'"
        )

    import_sections(iter(reader))


def import_enrollment(data: Iterator):
    model = EnrollmentHeader()
    header = process_header(model, next(data))

    for row in data:
        student_email = row[header.student_email_index]
        student_name = row[header.student_name_index]
        staff_email = row[header.staff_email_index]
        location = row[header.location_index]
        start_time = parse_time_string(row[header.day_index], row[header.start_index])
        section_type = row[header.type_index]

        student = offering_member(email=student_email)
        if student is None:
            student = find_or_add_person(student_email, student_name)
            student.set_role(get_course(), is_staff=False)

        staff = offering_member(email=staff_email)
        if staff is None:
            raise Failure(f"Unable to import enrollment data for {student_email}! {staff_email} isn't on staff.")

        # Assumes that each section can be uniquely identified by the below parameters
        section = Section.query.filter_by(
            staff=staff,
            course=get_course(),
            name=section_type,
            start_time=start_time,
            location=location
        ).one_or_none()

        if section is None:
            raise Failure(f"Unable to import enrollment data for {student_email}! Trying to enroll in {staff_email} | {location} | {start_time} | {section_type}")

        # If user is already in a section of the same type, remove it and add target section
        for s in student.sections:
            if s.name == section.name:
                student.sections.remove(s)
                break
        student.sections.append(section)
        db.session.add(student)

    db.session.commit()


def import_enrollment_from_url(url: str):
    try:
        reader = read_spreadsheet(
            url=url,
            sheet_name="Enrollment",
        )
    except Exception:
        raise Failure(
            "Unable to read spreadsheet. Make sure to put your data in a sheet named 'Enrollment'"
        )

    import_enrollment(iter(reader))