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

    # Section times are Integer columns; Postgres rejects a float like 1629817200.0.
    return int(datetime(
        year=2021,
        month=8,
        day=23 + day_offset,
        hour=hour + hour_offset,
        minute=min,
        tzinfo=pst
    ).timestamp())


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


def parse_capacity(capacity: str) -> int:
    try:
        capacity = int(capacity)
    except ValueError:
        raise Failure(f"Capacity must be a whole number, not '{capacity}'")
    if capacity < 0:
        raise Failure(f"Capacity can't be negative: {capacity}")
    return capacity


def check_capacity(section: Section, capacity: int):
    """Fail if ``section`` already has more students than ``capacity``."""
    if capacity < len(section.students):
        raise Failure(
            f"Can't set the capacity of the {section.name} section at {section.location} to {capacity}, "
            f"because {len(section.students)} students are already enrolled in it."
        )


def section_key(section_type, start_time, end_time, location):
    """What identifies a section when sections are re-imported: its type, time and place."""
    return section_type, start_time, end_time, location


def import_sections(data: Iterator):
    """Add the sheet's sections to the offering. A row that matches an existing
    section (same type, time and place, plus the same staff email when that
    alone is ambiguous) updates that section instead of adding a copy of it.
    Sections missing from the sheet are left alone.

    Returns ``(added, updated)``, the number of sections of each."""
    model = SectionsHeader()
    header = process_header(model, next(data))
    rows = list(data)

    existing = {}
    for section in Section.query.filter_by(course=get_course()):
        key = section_key(section.name, section.start_time, section.end_time, section.location)
        existing.setdefault(key, []).append(section)
    row_keys = [
        section_key(
            row[header.type_index],
            parse_time_string(row[header.day_index], row[header.start_index]),
            parse_time_string(row[header.day_index], row[header.end_index]),
            row[header.location_index],
        )
        for row in rows
    ]
    rows_per_key = {key: row_keys.count(key) for key in row_keys}
    matched = set()
    added = updated = 0

    for row, key in zip(rows, row_keys):
        email = row[header.email_index]
        name = row[header.name_index]
        capacity = parse_capacity(row[header.capacity_index])
        tags = row[header.tags_index]
        can_self_enroll = row[header.self_enroll_index].lower()
        if can_self_enroll not in ("false", "true"):
            raise Failure(f"Unknown boolean value: {can_self_enroll}")
        can_self_enroll = can_self_enroll == "true"

        staff = offering_member(email=email)
        if staff is None:
            staff = find_or_add_person(email, name)
            staff.set_role(get_course(), is_staff=True)

        candidates = [s for s in existing.get(key, []) if s.id not in matched]
        if len(existing.get(key, [])) > 1 or rows_per_key[key] > 1:
            # Several sections meet at this time and place (e.g. online), so
            # only the one with this staff member is the same section.
            candidates = [s for s in candidates if s.staff is not None and s.staff.id == staff.id]
        section = candidates[0] if len(candidates) == 1 else None

        if section is None:
            section_type, start_time, end_time, location = key
            section = Section(
                course=get_course(),
                name=section_type,  # In models.py, name refers to the type of section (Lab/Discussion/Custom)
                start_time=start_time,
                end_time=end_time,
                location=location,
            )
            db.session.add(section)
            added += 1
        else:
            check_capacity(section, capacity)
            matched.add(section.id)
            updated += 1

        section.capacity = capacity
        section.can_self_enroll = can_self_enroll
        section.staff = staff
        section.tags = tags.split(",")

    db.session.commit()
    return added, updated


def import_sections_from_url(url: str):
    try:
        reader = read_spreadsheet(
            url=url,
            sheet_name="Sections",
        )
    except Exception:
        raise Failure(
            "Unable to read spreadsheet. Make sure to put your data in a sheet named 'Sections' "
            "and ensure the sheet is visible to anyone with the link."
        )

    return import_sections(iter(reader))


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
        for s in student.sections_in(get_course()):
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
            "Unable to read spreadsheet. Make sure to put your data in a sheet named 'Enrollment' "
            "and ensure the sheet is visible to anyone with the link."
        )

    import_enrollment(iter(reader))