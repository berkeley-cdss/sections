"""Admins changing the course's settings, including its staff page link (#25)."""

from models import CourseConfig, db
from tests.unit.support import CourseTestCase


class StaffUrlTests(CourseTestCase):
    def course_config(self):
        return self.api("refresh_state").get_json()["data"]["config"]

    def test_no_link_until_an_admin_sets_one(self):
        self.assertIsNone(self.course_config()["staffUrl"])

    def test_admins_set_and_clear_the_link(self):
        self.make_staff_admin()
        self.course_config()  # creates the row, as loading any page does
        body = self.api("update_config", staff_url="  https://cs61a.org/staff/ ").get_json()
        self.assertTrue(body["success"], body)
        self.assertEqual(body["data"]["config"]["staffUrl"], "https://cs61a.org/staff/")
        body = self.api("update_config", staff_url="").get_json()
        self.assertIsNone(body["data"]["config"]["staffUrl"])

    def test_only_web_addresses(self):
        self.make_staff_admin()
        self.course_config()
        for url in ["javascript:alert(1)", "JavaScript://x/%0aalert(1)", "data:text/html,hi", "cs61a.org/staff",
                    "https://", "https://cs61a.org/st aff", "http://[oops", 5, "https://x/" + "a" * 1024]:
            with self.subTest(url=url):
                body = self.api("update_config", staff_url=url).get_json()
                self.assertFalse(body["success"])
        self.assertIsNone(self.course_config()["staffUrl"])
        self.assertTrue(self.api("update_config", staff_url="HTTP://Example.com").get_json()["success"])

    def test_only_admins(self):
        body = self.api("update_config", staff_url="https://cs61a.org/staff/").get_json()
        self.assertFalse(body.get("success", False))
        self.assertIsNone(self.course_config()["staffUrl"])

    def test_cannot_change_which_course_the_settings_belong_to(self):
        self.make_staff_admin()
        self.course_config()  # creates the row
        body = self.api("update_config", course="data8").get_json()
        self.assertFalse(body["success"])
        self.assertIn("Unknown setting: course", body["message"])
        self.assertEqual(CourseConfig.query.filter_by(course="cs61a").count(), 1)

    def test_toggles_still_save(self):
        self.make_staff_admin()
        self.course_config()
        body = self.api("update_config", can_students_join_lab=False).get_json()
        self.assertFalse(body["data"]["config"]["canStudentsJoinLab"])
