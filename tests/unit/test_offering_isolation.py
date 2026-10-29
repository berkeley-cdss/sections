"""Each course offering's sections, people and attendance stay separate."""

from models import Attendance, AttendanceStatus, Section, Session, User, db, set_contains
from tests.unit.support import CS61A, CourseTestCase, DATA8, UNSET_UP, canvas_course


class OfferingIsolationTests(CourseTestCase):
    def test_courses_are_isolated(self):
        state = self.api("refresh_state").get_json()["data"]
        self.assertEqual([s["location"] for s in state["sections"]], ["Room"])
        # Sections from another course can't be reached through this one.
        # The error handler reports the missing section as a 404.
        self.assertEqual(self.api("claim_section", section_id=str(self.data8_section_id)).status_code, 404)
        self.assertIsNone(db.session.get(Section, self.data8_section_id).staff_id)
        # Not enrolled in DATA 8, so its pages and APIs are forbidden.
        self.assertEqual(self.api("refresh_state", DATA8).status_code, 403)
        self.assertEqual(self.get(f"/offerings/{DATA8}/").status_code, 403)

    def test_one_person_in_two_offerings_sees_each_separately(self):
        known = self.enroll_known_in_data8()
        known.sections.append(db.session.get(Section, self.section_id))
        db.session.commit()
        self.sign_in(known)
        for canvas_id, location in ((CS61A, "Room"), (DATA8, "Elsewhere")):
            state = self.api("refresh_state", canvas_id).get_json()["data"]
            self.assertEqual([s["location"] for s in state["enrolledSections"]], [location])

    def test_joining_a_lab_keeps_the_lab_in_another_offering(self):
        known = self.enroll_known_in_data8()
        self.sign_in(known)
        self.api("refresh_state")  # the app loads state (and the course config) first
        result = self.api("join_section", target_section_id=str(self.section_id)).get_json()
        self.assertTrue(result["success"], result)
        db.session.remove()
        sections = {s.id for s in db.session.get(User, self.known_id).sections}
        self.assertEqual(sections, {self.section_id, self.data8_section_id})

    def test_leaving_and_removal_only_affect_this_offering(self):
        known = self.enroll_known_in_data8()
        known.sections.append(db.session.get(Section, self.section_id))
        db.session.commit()
        self.sign_in(known)
        self.api("refresh_state")  # the app loads state (and the course config) first
        self.assertTrue(self.api("leave_all_sections").get_json()["success"])
        db.session.remove()
        self.assertEqual([s.id for s in db.session.get(User, self.known_id).sections],
                         [self.data8_section_id])

        # Admins removing a student also leave their other offerings alone.
        known = db.session.get(User, self.known_id)
        known.sections.append(db.session.get(Section, self.section_id))
        staff = db.session.get(User, self.staff_id)
        staff.canvas_courses = {str(CS61A): canvas_course("CS 61A", staff=True, admin=True)}
        db.session.commit()
        self.sign_in(staff)
        self.assertTrue(self.api("remove_students", students="known@test").get_json()["success"])
        db.session.remove()
        self.assertEqual([s.id for s in db.session.get(User, self.known_id).sections],
                         [self.data8_section_id])

    def test_attendance_history_is_per_offering(self):
        known = self.enroll_known_in_data8()
        data8_session = Session(course=str(DATA8), start_time=0, section_id=self.data8_section_id)
        db.session.add(data8_session)
        db.session.add(Attendance(course=str(DATA8), status=AttendanceStatus.present,
                                  session=data8_session, student=known))
        db.session.commit()
        self.sign_in(known)
        for canvas_id, expected in ((CS61A, 0), (DATA8, 1)):
            user = self.api("refresh_state", canvas_id).get_json()["data"]["currentUser"]
            self.assertEqual(len(user["attendanceHistory"]), expected)

    def test_reset_removes_sections_and_assignments_but_keeps_people(self):
        known = self.enroll_known_in_data8()
        section = db.session.get(Section, self.section_id)
        known.sections.append(section)
        section.staff = db.session.get(User, self.staff_id)
        session = Session(course="cs61a", start_time=0, section=section)
        db.session.add(Attendance(course="cs61a", status=AttendanceStatus.present,
                                  session=session, student=known))
        staff = db.session.get(User, self.staff_id)
        staff.canvas_courses = {str(CS61A): canvas_course("CS 61A", staff=True, admin=True)}
        db.session.commit()

        self.assertTrue(self.api("reset_sections").get_json()["success"])
        db.session.remove()
        self.assertIsNone(db.session.get(Section, self.section_id))
        self.assertEqual(Session.query.filter_by(course="cs61a").count(), 0)
        self.assertEqual(Attendance.query.filter_by(course="cs61a").count(), 0)
        known = db.session.get(User, self.known_id)
        # Still in the course, and untouched in DATA 8.
        self.assertEqual(known.student_offerings, {"cs61a", str(DATA8)})
        self.assertEqual([s.id for s in known.sections], [self.data8_section_id])
        self.assertIn("cs61a", db.session.get(User, self.staff_id).staff_offerings)

    def test_global_admins_count_as_members_everywhere(self):
        boss = User(email="boss@test", name="Boss", canvas_id="9", is_global_admin=True)
        db.session.add(boss)
        db.session.commit()
        result = self.api("get_userid", email="boss@test").get_json()
        self.assertEqual(result["data"], boss.id)

    def test_offering_keys_match_exactly(self):
        dash = User(email="dash@test", name="Dash")
        dash.set_role("cs61a-tutoring", is_staff=False)
        db.session.add(dash)
        db.session.commit()
        # "_" is a LIKE wildcard; it must not match "-".
        self.assertEqual(User.query.filter(set_contains(User.student_offerings, "cs61a_tutoring")).count(), 0)
        self.assertEqual(User.query.filter(set_contains(User.student_offerings, "cs61a-tutoring")).count(), 1)

    def test_sessions_can_only_start_for_this_offerings_sections(self):
        # The error handler reports the missing section as a 404.
        self.assertEqual(self.api("start_session", section_id=str(self.data8_section_id), start_time=0).status_code,
                         404)
        self.assertEqual(Session.query.count(), 0)

    def test_course_that_is_not_set_up_is_not_found(self):
        self.assertEqual(self.api("refresh_state", UNSET_UP).status_code, 404)
