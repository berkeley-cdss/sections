from __future__ import annotations

import re
from datetime import datetime
from typing import List, Iterator

from zoneinfo import ZoneInfo

from offering import get_course
from google_sheets import read_spreadsheet
from dataclasses import asdict, dataclass, field, fields
from models import Failure, Section, check_fits, db, find_or_add_person, offering_member, user_section

# Sample Spreadsheet Link: https://docs.google.com/spreadsheets/d/1WL7gXiBxPe6aUFBKfEOVS6iY27ITy9mARupLoJX-ouE/edit?usp=sharing
pst = ZoneInfo("US/Pacific")


DAYS = ["M", "T", "W", "Th", "F"]
# 08:30a, as the Settings tab shows times, or 8:30 AM, as Google Sheets shows
# them (seconds optional, any case). am or pm is required: 10:00 is ambiguous.
TIME_FORMAT = re.compile(r"(\d\d?):(\d\d)(?::(\d\d))?\s?([ap])m?", re.IGNORECASE)


def parse_time_string(day, time, label="Time"):
    """Seconds since the epoch of ``time`` (e.g. "08:30a" or "8:30 AM") on
    ``day`` (e.g. "Th") in a fixed week. ``label`` names the time in error messages."""
    if day not in DAYS:
        raise Failure(f"Day must be one of {', '.join(DAYS)}, not '{day}'.")
    match = TIME_FORMAT.fullmatch(time.strip())
    if match is None:
        raise Failure(f"{label} must be a time with am or pm, like 8:30 AM, 2:15pm or 08:30a, not '{time}'.")
    hour, min, sec, ampm = int(match[1]), int(match[2]), int(match[3] or 0), match[4].lower()
    if not (1 <= hour <= 12 and min <= 59 and sec <= 59):
        raise Failure(f"{label} '{time}' isn't a time on a 12-hour clock.")

    day_offset = DAYS.index(day)
    # 12:30a is just after midnight and 12:30p just after noon.
    hour_offset = 12 if ampm == "p" else 0

    # Section times are Integer columns; Postgres rejects a float like 1629817200.0.
    return int(datetime(
        year=2021,
        month=8,
        day=23 + day_offset,
        hour=hour % 12 + hour_offset,
        minute=min,
        second=sec,
        tzinfo=pst
    ).timestamp())


def parse_section_times(day, start, end):
    """``(start, end)`` times of a section, which must end after it starts."""
    start_time = parse_time_string(day, start, "Start time")
    end_time = parse_time_string(day, end, "End time")
    if end_time <= start_time:
        raise Failure(f"End time {end} must be after start time {start}.")
    return start_time, end_time


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
            f"Can't set the capacity to {capacity}, "
            f"because {len(section.students)} students are already enrolled in this section."
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
    row_keys = []
    # Row numbers as in the spreadsheet, after the header in row 1.
    for row_number, row in enumerate(rows, start=2):
        try:
            start_time, end_time = parse_section_times(
                row[header.day_index], row[header.start_index], row[header.end_index])
        except Failure as failure:
            raise Failure(f"Row {row_number}: {failure}")
        row_keys.append(section_key(row[header.type_index], start_time, end_time, row[header.location_index]))
    rows_per_key = {key: row_keys.count(key) for key in row_keys}
    matched = set()
    added = updated = 0

    for row_number, (row, key) in enumerate(zip(rows, row_keys), start=2):
        try:
            check_fits("Type", row[header.type_index], Section.name)
            check_fits("Location", row[header.location_index], Section.location)
            check_fits("Tags", row[header.tags_index], Section.tag_string)
        except Failure as failure:
            raise Failure(f"Row {row_number}: {failure}")
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
            try:
                check_capacity(section, capacity)
            except Failure as failure:
                raise Failure(f"Row {row_number}: {failure}")
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

    for row_number, row in enumerate(data, start=2):
        student_email = row[header.student_email_index]
        student_name = row[header.student_name_index]
        staff_email = row[header.staff_email_index]
        location = row[header.location_index]
        try:
            start_time = parse_time_string(row[header.day_index], row[header.start_index], "Start time")
        except Failure as failure:
            raise Failure(f"Row {row_number}: {failure}")
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