"""Admins editing a section's staff, capacity, day and time."""

from unittest.mock import patch

from canvasapi.exceptions import InvalidAccessToken

from server.import_sheet import parse_time_string
from server.models import Section, User, db
from tests.unit.support import CS61A, CourseTestCase, DATA8, canvas_course


class SectionSettingsTests(CourseTestCase):
    def test_call_links_must_be_web_addresses(self):
        def set_link(link):
            return self.api("update_section_call_link", section_id=str(self.section_id), call_link=link).get_json()

        for link in ["javascript:alert(1)", "JavaScript://x/%0aalert(1)", "data:text/html,hi",
                     "zoom.us/j/123", "https://", "https://zoom.us/j/1 23", 5]:
            with self.subTest(link=link):
                body = set_link(link)
                self.assertFalse(body["success"])
        self.assertIsNone(db.session.get(Section, self.section_id).call_link)
        self.assertIn("must be a web address", set_link("zoom.us/j/123")["message"])

        def saved():
            db.session.remove()
            return db.session.get(Section, self.section_id).call_link

        self.assertTrue(set_link("  https://berkeley.zoom.us/j/123 ")["success"])
        self.assertEqual(saved(), "https://berkeley.zoom.us/j/123")
        self.assertTrue(set_link("")["success"])
        self.assertIsNone(saved())  # a blank link removes it

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
            (("M", "10am", "11:00a"), "Start time must be a time with am or pm"),
            (("M", "10:00a", "11:00"), "End time must be a time with am or pm"),
            (("M", "10:00x", "11:00x"), "Start time must be a time with am or pm"),
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


class StaffPickerCanvasTests(CourseTestCase):
    """The staff picker asks Canvas about people whose saved roles are out of date."""

    def setUp(self):
        super().setUp()
        self.make_staff_admin()
        # Signed in last semester as a student in an old course, before CS 61A.
        returning = User(email="returning@test", name="Returning", canvas_id="77",
                         canvas_courses={"999": canvas_course("CS 10", student=True)})
        db.session.add(returning)
        db.session.commit()
        self.returning_id = returning.id

    def canvas_staff(self, staff=None, **kwargs):
        """Canvas's current CS 61A staff, {canvas user id: is_admin}."""
        return patch("server.state.canvas_service.get_course_staff", return_value=staff, **kwargs)

    def staff_emails(self):
        return [person["email"] for person in self.api("list_staff").get_json()["data"]]

    def assign_returning(self):
        return self.api("update_section_staff", section_id=str(self.section_id),
                        staff_id=str(self.returning_id)).get_json()

    def test_last_semesters_student_on_staff_now_is_listed_and_assignable(self):
        self.authorize()
        with self.canvas_staff({"77": False, "1": True}) as lookup:
            self.assertEqual(self.staff_emails(), ["returning@test", "staff@test"])
            body = self.assign_returning()
        self.assertEqual(lookup.call_args.args, ("access",))  # the signed-in admin's token
        self.assertEqual(body["data"]["staff"]["email"], "returning@test")
        db.session.remove()
        returning = db.session.get(User, self.returning_id)
        self.assertIn("cs61a", returning.staff_offerings)
        self.assertNotIn("cs61a", returning.admin_offerings)

    def test_lead_tas_become_admins(self):
        self.authorize()
        with self.canvas_staff({"77": True}):
            self.assertTrue(self.assign_returning()["success"])
        db.session.remove()
        self.assertIn("cs61a", db.session.get(User, self.returning_id).admin_offerings)

    def test_not_listed_or_assignable_unless_canvas_lists_them(self):
        self.authorize()
        with self.canvas_staff({"1": True}):
            self.assertEqual(self.staff_emails(), ["staff@test"])
            body = self.assign_returning()
        self.assertEqual(body, {"success": False, "message": "That person isn't on staff in this course."})

    def test_canvas_is_not_asked_to_assign_people_saved_roles_show(self):
        other = User(email="other@test", name="Other")
        other.set_role("cs61a", is_staff=True)
        db.session.add(other)
        db.session.commit()
        with self.canvas_staff({}) as lookup:
            body = self.api("update_section_staff", section_id=str(self.section_id),
                            staff_id=str(other.id)).get_json()
        self.assertTrue(body["success"], body)
        lookup.assert_not_called()

    def test_without_a_current_canvas_token(self):
        for authorize in (False, True):  # no token, then an expired one
            with self.subTest(authorize=authorize):
                if authorize:
                    self.authorize(expires_in=-10)
                with self.canvas_staff({"77": False}) as lookup:
                    self.assertEqual(self.staff_emails(), ["staff@test"])
                    body = self.assign_returning()
                lookup.assert_not_called()
                self.assertFalse(body["success"])
                self.assertIn("needs a current Canvas sign-in", body["message"])

    def test_a_rejected_token_counts_as_none(self):
        self.authorize()
        with self.canvas_staff(side_effect=InvalidAccessToken("revoked")):
            self.assertEqual(self.staff_emails(), ["staff@test"])
            self.assertIn("needs a current Canvas sign-in", self.assign_returning()["message"])

    def test_the_list_still_loads_if_canvas_fails(self):
        self.authorize()
        with self.canvas_staff(side_effect=ConnectionError("Canvas is down")), \
                self.assertLogs(self.app.logger, "ERROR"):
            self.assertEqual(self.staff_emails(), ["staff@test"])

