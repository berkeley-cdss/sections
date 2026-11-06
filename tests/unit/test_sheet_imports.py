"""Importing sections and enrollment from a spreadsheet, and importing sections again."""

from unittest.mock import patch

from flask import g

from server.import_sheet import import_enrollment, import_sections, parse_time_string
from server.models import Failure, Offering, Section, User, db
from tests.unit.support import CS61A, DATA8, CourseTestCase, canvas_course


class SheetImportsTests(CourseTestCase):
    def test_enrollment_import_keeps_same_type_sections_in_other_offerings(self):
        self.enroll_known_in_data8()  # in DATA 8's Lab
        cs61a_lab = db.session.get(Section, self.section_id)
        cs61a_lab.staff = db.session.get(User, self.staff_id)
        cs61a_lab.start_time = parse_time_string("M", "10:00a")
        db.session.commit()
        with self.app.test_request_context():
            g.offering = Offering.query.filter_by(canvas_id=CS61A).one()
            import_enrollment(iter([
                ["Student Email", "Student Name", "Staff Email", "Location", "Day", "Start", "Type"],
                ["known@test", "Known", "staff@test", "Room", "M", "10:00a", "Lab"],
            ]))
        db.session.remove()
        sections = {s.id for s in db.session.get(User, self.known_id).sections}
        self.assertEqual(sections, {self.section_id, self.data8_section_id})

    def test_times_can_be_written_as_google_sheets_shows_them(self):
        eight_thirty = parse_time_string("M", "08:30a")
        for time in ("8:30a", "8:30 AM", "8:30am", "08:30 am", "8:30 A", " 8:30 AM "):
            with self.subTest(time=time):
                self.assertEqual(parse_time_string("M", time), eight_thirty)
        self.assertEqual(parse_time_string("M", "8:30:00 AM"), eight_thirty)
        self.assertEqual(parse_time_string("M", "8:30:15 AM"), eight_thirty + 15)
        self.assertEqual(parse_time_string("M", "2:15 PM"), parse_time_string("M", "02:15p"))
        # 12 AM is midnight and 12 PM is noon.
        self.assertEqual(parse_time_string("M", "12:30 PM") - parse_time_string("M", "12:30 AM"), 12 * 3600)
        self.assertEqual(parse_time_string("M", "12:30 AM"), eight_thirty - 8 * 3600)
        for time in ("10:00", "10am", "8:30 AMX", "8:30  AM", "13:00 PM", "0:30 AM", "8:30:60 AM"):
            with self.subTest(time=time), self.assertRaises(Failure):
                parse_time_string("M", time)

    def test_sheet_times_are_integers(self):
        # Section times are Integer columns. Postgres rejects a float such as
        # 1629817200.0; SQLite silently stores it, so check before it's saved.
        self.assertEqual(parse_time_string("T", "08:00a"), 1629817200)  # Tue 2021-08-24 8am PDT
        with self.app.test_request_context(), patch.object(db.session, "commit"):
            g.offering = Offering.query.filter_by(canvas_id=CS61A).one()
            import_sections(iter([
                ["Email", "Name", "Capacity", "Location", "Day", "Start", "End", "Tags", "Can Self Enroll", "Type"],
                ["staff@test", "Staff", "35", "The Moon", "T", "08:00a", "09:30p", "", "TRUE", "Lab"],
            ]))
            [section] = [s for s in db.session.new if isinstance(s, Section)]
            self.assertEqual((section.start_time, section.end_time), (1629817200, 1629865800))
            self.assertIs(type(section.start_time), int)
            self.assertIs(type(section.end_time), int)

    def test_reimporting_sections_updates_them_instead_of_duplicating(self):
        rows = [
            ["staff@test", "Staff", "30", "Room A", "M", "10:00a", "11:00a", "", "TRUE", "Lab"],
            ["staff@test", "Staff", "30", "Room B", "M", "10:00a", "11:00a", "", "TRUE", "Lab"],
        ]
        self.assertEqual(self.import_cs61a_sections(*rows), (2, 0))
        room_a = Section.query.filter_by(course="cs61a", location="Room A").one()
        room_a.students.append(db.session.get(User, self.known_id))
        db.session.commit()
        room_a_id = room_a.id

        # A new TA, a bigger room, and a new section.
        rows[0] = ["new@test", "New TA", "40", "Room A", "M", "10:00a", "11:00a", "Scholars", "FALSE", "Lab"]
        rows.append(["staff@test", "Staff", "30", "Room C", "T", "10:00a", "11:00a", "", "TRUE", "Lab"])
        self.assertEqual(self.import_cs61a_sections(*rows), (1, 2))
        self.assertEqual(Section.query.filter_by(course="cs61a", location="Room A").count(), 1)
        room_a = db.session.get(Section, room_a_id)
        self.assertEqual((room_a.staff.email, room_a.capacity, room_a.tags, room_a.can_self_enroll),
                         ("new@test", 40, ["Scholars"], False))
        self.assertEqual([s.id for s in room_a.students], [self.known_id])
        # The section from setUp, at another time, is left alone.
        self.assertIsNotNone(db.session.get(Section, self.section_id))

    def test_reimport_tells_sections_at_the_same_time_and_place_apart_by_staff(self):
        other = User(email="other@test", name="Other")
        other.set_role("cs61a", is_staff=True)
        db.session.add(other)
        db.session.commit()
        rows = [
            ["staff@test", "Staff", "30", "Online", "M", "10:00a", "11:00a", "", "TRUE", "Discussion"],
            ["other@test", "Other", "30", "Online", "M", "10:00a", "11:00a", "", "TRUE", "Discussion"],
        ]
        self.assertEqual(self.import_cs61a_sections(*rows), (2, 0))
        rows[1][2] = "50"
        self.assertEqual(self.import_cs61a_sections(*rows), (0, 2))
        capacities = {s.staff.email: s.capacity for s in Section.query.filter_by(location="Online")}
        self.assertEqual(capacities, {"staff@test": 30, "other@test": 50})

    def test_reimport_cannot_shrink_a_section_below_its_enrollment(self):
        section = db.session.get(Section, self.section_id)
        section.students.append(db.session.get(User, self.known_id))
        db.session.commit()
        with self.assertRaisesRegex(Exception, "^Row 2: .*1 students are already enrolled"):
            # setUp's lab is in Room from 0 to 3600, which isn't a weekday time,
            # so match it directly.
            with patch("server.import_sheet.parse_time_string", side_effect=[0, 3600]):
                self.import_cs61a_sections(
                    ["staff@test", "Staff", "0", "Room", "M", "10:00a", "11:00a", "", "TRUE", "Lab"])
        db.session.remove()
        self.assertEqual(db.session.get(Section, self.section_id).capacity, 30)

    def test_sheet_time_errors_name_the_row(self):
        with self.assertRaisesRegex(Exception, "^Row 3: End time 09:00a must be after start time 10:00a."):
            self.import_cs61a_sections(
                ["staff@test", "Staff", "30", "Room A", "M", "10:00a", "11:00a", "", "TRUE", "Lab"],
                ["staff@test", "Staff", "30", "Room B", "M", "10:00a", "09:00a", "", "TRUE", "Lab"])
        self.assertEqual(Section.query.filter_by(location="Room A").count(), 0)


class SheetImportStaffTests(CourseTestCase):
    """Imports only make course staff a section's TA."""

    def lab_row(self, email, name="Someone", location="Room Z"):
        return [email, name, "30", location, "M", "10:00a", "11:00a", "", "TRUE", "Lab"]

    def add_user(self, email, *, canvas_courses=None, staff_in=(), student_in=()):
        user = User(email=email, name=email, canvas_id=email if canvas_courses is not None else None,
                    canvas_courses=canvas_courses)
        for key in staff_in:
            user.set_role(key, is_staff=True)
        for key in student_in:
            user.set_role(key, is_staff=False)
        db.session.add(user)
        db.session.commit()
        return user.id

    def assert_refused(self, email, row_number=2):
        with self.assertRaisesRegex(Failure, f"^Row {row_number}: {email} isn't on staff in this course."):
            self.import_cs61a_sections(self.lab_row("staff@test", location="Room Y"), self.lab_row(email))
        db.session.remove()
        self.assertEqual(Section.query.filter(Section.location.in_(["Room Y", "Room Z"])).count(), 0)

    def test_students_are_refused(self):
        self.assert_refused("known@test", row_number=3)  # a student in Canvas
        # Imported as a student, and hasn't signed in.
        self.add_user("imported@test", student_in=["cs61a"])
        self.assert_refused("imported@test", row_number=3)

    def test_people_not_on_staff_here_in_canvas_are_refused(self):
        # Signed in for DATA 8, where they're on staff, but not in CS 61A.
        self.add_user("data8@test", canvas_courses={str(DATA8): canvas_course("DATA 8", staff=True)},
                      staff_in=[str(DATA8)])
        self.assert_refused("data8@test", row_number=3)
        # Staff here in Sections, but no longer in Canvas.
        self.add_user("former@test", canvas_courses={str(CS61A): canvas_course("CS 61A", student=True)},
                      staff_in=["cs61a"])
        self.assert_refused("former@test", row_number=3)

    def test_staff_in_canvas_who_have_not_opened_the_course_become_staff(self):
        user_id = self.add_user("new-ta@test", canvas_courses={str(CS61A): canvas_course("CS 61A", staff=True)})
        self.assertEqual(self.import_cs61a_sections(self.lab_row("new-ta@test")), (1, 0))
        user = db.session.get(User, user_id)
        self.assertIn("cs61a", user.staff_offerings)
        self.assertNotIn("cs61a", user.admin_offerings)
        self.assertEqual(Section.query.filter_by(location="Room Z").one().staff_id, user_id)

    def test_emails_nobody_has_signed_in_with_become_staff(self):
        # A new email, and one imported for another course.
        other_id = self.add_user("other-course@test", staff_in=[str(DATA8)])
        self.assertEqual(self.import_cs61a_sections(
            self.lab_row("brand-new@test"), self.lab_row("other-course@test", location="Room Y")), (2, 0))
        for email in ("brand-new@test", "other-course@test"):
            self.assertIn("cs61a", User.query.filter_by(email=email).one().staff_offerings)
        self.assertIn(str(DATA8), db.session.get(User, other_id).staff_offerings)

    def test_enrollment_staff_email_must_be_on_staff(self):
        with self.app.test_request_context():
            g.offering = Offering.query.filter_by(canvas_id=CS61A).one()
            with self.assertRaisesRegex(Failure, "^Row 2: known@test isn't on staff in this course."):
                import_enrollment(iter([
                    ["Student Email", "Student Name", "Staff Email", "Location", "Day", "Start", "Type"],
                    ["new-student@test", "New", "known@test", "Room", "M", "10:00a", "Lab"],
                ]))
