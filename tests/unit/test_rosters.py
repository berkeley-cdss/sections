"""What each person can see of section rosters."""

from flask import g

from models import Offering, Section, User, db
from tests.unit.support import CS61A, CourseTestCase


class RostersTests(CourseTestCase):
    def test_student_refresh_uses_summaries_and_keeps_enrolled_roster(self):
        known = db.session.get(User, self.known_id)
        section = db.session.get(Section, self.section_id)
        peer = User(email="peer@test", name="Peer")
        unrelated = User(email="unrelated@test", name="Unrelated")
        for person in (peer, unrelated):
            person.set_role("cs61a", is_staff=False)
        other_section = Section(course="cs61a", name="Discussion", location="Other Room",
                                description="", capacity=25, can_self_enroll=True,
                                start_time=7200, end_time=10800)
        section.students.extend([known, peer])
        other_section.students.append(unrelated)
        db.session.add_all([peer, unrelated, other_section])
        db.session.commit()

        self.sign_in(self.known)
        response = self.api("refresh_state")

        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertTrue(result["success"])
        state = result["data"]
        self.assertEqual(state["course"], "CS 61A")
        self.assertEqual(state["currentUser"]["id"], self.known_id)
        summaries = {item["id"]: item for item in state["sections"]}

        enrolled_summary = summaries[str(self.section_id)]
        other_summary = summaries[str(other_section.id)]
        self.assertEqual(enrolled_summary["enrollmentCount"], 2)
        self.assertEqual(len(enrolled_summary["students"]), 2)
        self.assertEqual(enrolled_summary["students"], [None, None])
        self.assertEqual(other_summary["enrollmentCount"], 1)
        self.assertEqual(other_summary["students"], [None])

        self.assertEqual(len(state["enrolledSections"]), 1)
        roster = state["enrolledSections"][0]["students"]
        self.assertEqual(
            {student["email"] for student in roster},
            {"known@test", "peer@test"},
        )
        self.assertNotIn("unrelated@test", response.get_data(as_text=True))

    def test_pronouns_show_only_where_the_name_does(self):
        known = db.session.get(User, self.known_id)
        section = db.session.get(Section, self.section_id)
        peer = User(email="peer@test", name="Peer", pronouns="they/them")
        unrelated = User(email="unrelated@test", name="Unrelated", pronouns="he/him")
        for person in (peer, unrelated):
            person.set_role("cs61a", is_staff=False)
        section.students.extend([known, peer])
        db.session.add_all([peer, unrelated])
        db.session.commit()
        self.sign_in(known)
        roster = self.api("refresh_state").get_json()["data"]["enrolledSections"][0]["students"]
        self.assertIn({"name": "Peer", "pronouns": "they/them"},
                      [{"name": p["name"], "pronouns": p["pronouns"]} for p in roster])
        # A classmate outside your sections is anonymized, pronouns included.
        with self.app.test_request_context():
            g.offering = Offering.query.filter_by(canvas_id=CS61A).one()
            g._login_user = db.session.get(User, self.known_id)
            hidden = db.session.get(User, unrelated.id).json
        self.assertEqual((hidden["name"], hidden["pronouns"]), ("Anon Student", None))
