"""Exporting every student with their sections, and finding a student's sections."""

import csv
from io import StringIO

from server.models import Section, User, db
from server.state import csv_safe
from tests.unit.support import CourseTestCase, lab

# 2026-08-20 15:00 UTC is Thursday 08:00 in Berkeley.
THURSDAY_8AM = 1787238000


def discussion(course, location="Disc Room"):
    return Section(course=course, name="Discussion", location=location, description="",
                   capacity=30, can_self_enroll=True, start_time=THURSDAY_8AM, end_time=THURSDAY_8AM + 3600)


class StudentExportTests(CourseTestCase):
    def setUp(self):
        super().setUp()
        self.make_staff_admin()

    def export(self):
        body = self.api("export_students").get_json()
        self.assertTrue(body["success"], body)
        custom = body["data"]["custom"]
        self.assertEqual(custom["fileName"], "students.csv")
        return list(csv.reader(StringIO(custom["students"])))

    def test_lists_each_students_sections_or_floating(self):
        known = db.session.get(User, self.known_id)
        staff = db.session.get(User, self.staff_id)
        disc = discussion("cs61a")
        disc.staff = staff
        floater = User(email="floater@test", name="Floater")
        floater.set_role("cs61a", is_staff=False)
        known.sections.extend([db.session.get(Section, self.section_id), disc])
        db.session.add_all([disc, floater])
        db.session.commit()

        rows = self.export()
        self.assertEqual(rows[0], ["Name", "Email", "Lab", "Discussion"])
        self.assertEqual(rows[1:], [
            ["Floater", "floater@test", "Floating", "Floating"],
            ["Known", "known@test", "Staff, W 04:00p, Room", "Staff, Th 08:00a, Disc Room"],
        ])

    def test_leaves_staff_and_other_offerings_out(self):
        self.enroll_known_in_data8()
        rows = self.export()
        # Only known is a cs61a student; data8's lab isn't a column of its own.
        self.assertEqual(rows, [["Name", "Email", "Lab"], ["Known", "known@test", "Floating"]])

    def test_tutoring_isnt_floating(self):
        tutoring = Section(course="cs61a", name="Tutoring", location="T", description="",
                           capacity=5, can_self_enroll=True, start_time=0, end_time=3600)
        db.session.add(tutoring)
        db.session.commit()
        self.assertEqual(self.export()[1], ["Known", "known@test", "Floating", ""])

    def test_neutralizes_formulas(self):
        known = db.session.get(User, self.known_id)
        known.name = "=HYPERLINK(\"http://evil\",\"x\")"
        db.session.commit()
        self.assertEqual(self.export()[1][0], "'=HYPERLINK(\"http://evil\",\"x\")")



class StudentExportPermissionTests(CourseTestCase):
    def test_admins_only(self):
        body = self.api("export_students").get_json()  # signed in as staff, not admin
        self.assertFalse(body["success"])
        self.assertIn("Only course admins", body["message"])


class RosterExportFormulaTests(CourseTestCase):
    def test_roster_export_neutralizes_formulas(self):
        self.make_staff_admin()
        section = db.session.get(Section, self.section_id)
        section.location = "@SUM(A1)"
        section.students.append(db.session.get(User, self.known_id))
        db.session.commit()
        rosters = self.api("export_rosters").get_json()["data"]["custom"]["rosters"]
        self.assertEqual(list(csv.reader(StringIO(rosters)))[1][2], "'@SUM(A1)")


class CsvSafeTests(CourseTestCase):
    def test_csv_safe(self):
        for value, expected in [("=1+1", "'=1+1"), ("+1", "'+1"), ("-1", "'-1"), ("@x", "'@x"),
                                ("\tx", "'\tx"), ("\rx", "'\rx"), ("a=b", "a=b"), ("", ""), (None, "")]:
            self.assertEqual(csv_safe(value), expected)


class StudentSearchTests(CourseTestCase):
    def search(self, query):
        body = self.api("search_students", query=query).get_json()
        self.assertTrue(body["success"], body)
        return body["data"]

    def test_finds_by_name_or_email_with_sections(self):
        known = db.session.get(User, self.known_id)
        known.sections.append(db.session.get(Section, self.section_id))
        db.session.commit()

        for query in ("KNO", "known@", " now "):
            results = self.search(query)
            self.assertEqual([r["email"] for r in results], ["known@test"], query)
        [section] = results[0]["sections"]
        self.assertEqual((section["id"], section["name"], section["location"], section["staff"]["name"]),
                         (str(self.section_id), "Lab", "Room", "Staff"))

    def test_only_this_offerings_students_and_sections(self):
        self.enroll_known_in_data8()
        self.assertEqual(self.search("staff"), [])  # staff aren't students
        self.assertEqual(self.search("known")[0]["sections"], [])  # their data8 lab isn't here

    def test_wildcards_are_literal(self):
        self.assertEqual(self.search("%"), [])
        self.assertEqual(self.search("_"), [])
        self.assertEqual(self.search(""), [])

    def test_students_cant_search(self):
        self.sign_in(db.session.get(User, self.known_id))
        body = self.api("search_students", query="known").get_json()
        self.assertFalse(body["success"])
        self.assertIn("Only staff", body["message"])
