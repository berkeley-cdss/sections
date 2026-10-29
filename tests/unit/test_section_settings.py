"""Admins editing a section's staff, capacity, day and time."""

from import_sheet import parse_time_string
from models import Section, User, db
from tests.unit.support import CS61A, CourseTestCase, DATA8, canvas_course


class SectionSettingsTests(CourseTestCase):
    def test_admins_edit_capacity_but_not_below_enrollment(self):
        self.make_staff_admin()
        section = db.session.get(Section, self.section_id)
        section.students.append(db.session.get(User, self.known_id))
        db.session.commit()
        response = self.api("update_section_capacity", section_id=str(self.section_id), capacity="0").get_json()
        self.assertFalse(response["success"])
        self.assertIn("1 students are already enrolled", response["message"])
        response = self.api("update_section_capacity", section_id=str(self.section_id), capacity="1").get_json()
        self.assertTrue(response["success"])
        self.assertEqual(response["data"]["capacity"], 1)

    def test_admins_reassign_a_section_to_another_staff_member(self):
        self.make_staff_admin()
        other = User(email="other@test", name="Other")
        other.set_role("cs61a", is_staff=True)
        db.session.add(other)
        db.session.commit()
        staff_list = self.api("list_staff").get_json()["data"]
        self.assertEqual([person["email"] for person in staff_list], ["other@test", "staff@test"])
        section_id = str(self.section_id)
        response = self.api("update_section_staff", section_id=section_id, staff_id=str(other.id)).get_json()
        self.assertEqual(response["data"]["staff"]["email"], "other@test")
        response = self.api("update_section_staff", section_id=section_id, staff_id=str(self.known_id)).get_json()
        self.assertFalse(response["success"])  # a student, not staff
        response = self.api("update_section_staff", section_id=section_id, staff_id="").get_json()
        self.assertIsNone(response["data"]["staff"])

    def test_staff_list_follows_canvas_for_people_who_have_signed_in(self):
        self.make_staff_admin()
        people = {
            # On staff in Canvas, but hasn't opened this course in Sections yet.
            "new-ta@test": User(email="new-ta@test", name="New TA", canvas_id="10", canvas_courses={
                str(CS61A): canvas_course("CS 61A", staff=True)}),
            # Removed from the Canvas course after opening it here as staff.
            "gone-ta@test": User(email="gone-ta@test", name="Gone TA", canvas_id="11", canvas_courses={
                str(DATA8): canvas_course("DATA 8", staff=True)}),
            # Imported from a spreadsheet; hasn't signed in.
            "imported@test": User(email="imported@test", name="Imported"),
            # Global admins, who are staff everywhere, but only listed where
            # they're on staff in Canvas.
            "admin@test": User(email="admin@test", name="Admin", canvas_id="12", is_global_admin=True),
            "admin-ta@test": User(email="admin-ta@test", name="Admin TA", canvas_id="14", is_global_admin=True,
                                  canvas_courses={str(CS61A): canvas_course("CS 61A", staff=True)}),
            # On staff in another course only.
            "data8-ta@test": User(email="data8-ta@test", name="DATA 8 TA", canvas_id="13", canvas_courses={
                str(DATA8): canvas_course("DATA 8", staff=True)}),
        }
        people["gone-ta@test"].set_role("cs61a", is_staff=True)
        people["imported@test"].set_role("cs61a", is_staff=True)
        db.session.add_all(people.values())
        db.session.commit()

        staff_list = self.api("list_staff").get_json()["data"]
        self.assertEqual([person["email"] for person in staff_list],
                         ["admin-ta@test", "imported@test", "new-ta@test", "staff@test"])

        new_ta_id = people["new-ta@test"].id
        response = self.api("update_section_staff", section_id=str(self.section_id),
                            staff_id=str(new_ta_id)).get_json()
        self.assertEqual(response["data"]["staff"]["email"], "new-ta@test")
        db.session.remove()
        self.assertIn("cs61a", db.session.get(User, new_ta_id).staff_offerings)
        for email in ("gone-ta@test", "data8-ta@test", "admin@test"):
            response = self.api("update_section_staff", section_id=str(self.section_id),
                                staff_id=str(User.query.filter_by(email=email).one().id)).get_json()
            self.assertFalse(response["success"])

    def test_section_times_must_be_valid_and_end_after_they_start(self):
        self.make_staff_admin()
        cases = [
            (("m", "10:00a", "11:00a"), "Day must be one of M, T, W, Th, F, not 'm'."),
            (("M", "10am", "11:00a"), "Start time must be hh:mm followed by a or p"),
            (("M", "8:30a", "09:30a"), "Start time must be hh:mm followed by a or p"),
            (("M", "10:00a", "11:00"), "End time must be hh:mm followed by a or p"),
            (("M", "10:00x", "11:00x"), "Start time must be hh:mm followed by a or p"),
            (("M", "13:00p", "02:00p"), "Start time '13:00p' isn't a time on a 12-hour clock."),
            (("M", "11:00a", "10:00a"), "End time 10:00a must be after start time 11:00a."),
            (("M", "10:00a", "10:00a"), "End time 10:00a must be after start time 10:00a."),
        ]
        for (day, start, end), message in cases:
            with self.subTest(day=day, start=start, end=end):
                response = self.api("update_section_time", section_id=str(self.section_id),
                                    day=day, start_time=start, end_time=end).get_json()
                self.assertFalse(response["success"])
                self.assertIn(message, response["message"])
        response = self.api("update_section_time", section_id=str(self.section_id),
                            day="Th", start_time="11:30a", end_time="12:30p").get_json()
        self.assertTrue(response["success"])
        self.assertEqual((response["data"]["startTime"], response["data"]["endTime"]),
                         (parse_time_string("Th", "11:30a"), parse_time_string("Th", "11:30a") + 3600))

    def test_staff_who_are_not_admins_cannot_edit_staff_or_capacity(self):
        self.assertFalse(self.api("list_staff").get_json()["success"])
        for method, args in (("update_section_staff", {"staff_id": ""}),
                             ("update_section_capacity", {"capacity": "50"})):
            response = self.api(method, section_id=str(self.section_id), **args).get_json()
            self.assertFalse(response["success"])
