"""The /offerings pages: listing, importing and removing course offerings."""

from models import Offering, Section, db
from tests.unit.support import CS61A, CourseTestCase, DATA8, UNSET_UP, canvas_course, lab


class OfferingsPagesTests(CourseTestCase):
    def test_staff_import_offerings_and_students_cannot(self):
        self.sign_in(self.known)
        self.post("/offerings/new", data={"offerings": [str(UNSET_UP)]})
        self.assertIsNone(Offering.query.filter_by(canvas_id=UNSET_UP).one_or_none())

        self.sign_in(self.staff)
        page = self.get("/offerings/new").get_data(as_text=True)
        self.assertIn(f'value="{UNSET_UP}"', page)
        self.assertIn("2026-08 | CS 70 | CS 70 - LEC 001", page)
        self.assertNotIn(f'value="{CS61A}"', page)  # already set up
        # Only courses the user is staff in can be imported.
        response = self.post("/offerings/new", data={"offerings": [str(UNSET_UP), str(DATA8), "999"]})
        self.assertTrue(response.headers["Location"].endswith("/offerings"))
        offering = Offering.query.filter_by(canvas_id=UNSET_UP).one()
        self.assertEqual((offering.key, offering.code, offering.start_month), (str(UNSET_UP), "CS 70", "2026-08"))
        self.assertIsNone(Offering.query.filter_by(canvas_id=999).one_or_none())
        self.assertTrue(self.api("refresh_state", UNSET_UP).get_json()["success"])

    def test_offerings_page_matches_seating(self):
        self.assertTrue(self.get("/").headers["Location"].endswith("/offerings"))
        page = self.get("/offerings").get_data(as_text=True)
        self.assertIn("Staff Course Offerings", page)
        self.assertIn(f'href="/offerings/{CS61A}/"', page)
        self.assertNotIn(f"/offerings/{DATA8}/", page)
        # The linked offering picked up its Canvas details.
        self.assertIn("CS 61A - LEC 001", page)
        self.assertEqual(Offering.query.filter_by(canvas_id=CS61A).one().code, "CS 61A")
        self.assertEqual(self.api("refresh_state").get_json()["data"]["course"], "CS 61A")

        self.sign_in(self.known)
        page = self.get("/offerings").get_data(as_text=True)
        student_part = page[page.index("Student Course Offerings"):page.index("Other Course Offerings")]
        self.assertIn(f'href="/offerings/{CS61A}/"', student_part)
        self.assertNotIn("/remove", page)  # only staff offerings can be removed

    def test_staff_remove_offerings_and_keep_their_data(self):
        page = self.get("/offerings").get_data(as_text=True)
        self.assertIn(f'action="/offerings/{CS61A}/remove"', page)

        # Students, and staff of other courses, cannot.
        self.sign_in(self.known)
        self.assertEqual(self.post(f"/offerings/{CS61A}/remove").status_code, 403)
        self.sign_in(self.staff)
        self.assertEqual(self.post(f"/offerings/{DATA8}/remove").status_code, 403)
        self.assertEqual(self.post("/offerings/999/remove").status_code, 404)
        # Only a POST removes one. (A GET falls through to the React build's
        # static route, so it's a 404 rather than a 405.)
        self.assertEqual(self.get(f"/offerings/{CS61A}/remove").status_code, 404)
        self.assertIsNotNone(Offering.query.filter_by(canvas_id=CS61A).one_or_none())

        # A course linked from the monorepo: removing it keeps its sections under
        # "cs61a", and the message says how to link them again.
        response = self.post(f"/offerings/{CS61A}/remove", follow_redirects=True)
        self.assertIn(f"flask link-offering {CS61A} cs61a", response.get_data(as_text=True))
        self.assertIsNone(Offering.query.filter_by(canvas_id=CS61A).one_or_none())
        self.assertNotIn(f"/offerings/{CS61A}/", self.get("/offerings").get_data(as_text=True))
        self.assertIsNotNone(db.session.get(Section, self.section_id))
        self.app.test_cli_runner().invoke(args=["link-offering", str(CS61A), "cs61a", "CS 61A"])
        sections = self.api("refresh_state").get_json()["data"]["sections"]
        self.assertEqual([s["id"] for s in sections], [str(self.section_id)])

        # A course imported here comes back with its sections by importing it again.
        self.post("/offerings/new", data={"offerings": [str(UNSET_UP)]})
        db.session.add(lab(str(UNSET_UP)))
        db.session.commit()
        response = self.post(f"/offerings/{UNSET_UP}/remove", follow_redirects=True)
        self.assertIn("import it again to restore them", response.get_data(as_text=True))
        self.post("/offerings/new", data={"offerings": [str(UNSET_UP)]})
        self.assertEqual(len(self.api("refresh_state", UNSET_UP).get_json()["data"]["sections"]), 1)

    def test_offerings_without_a_start_date_say_so(self):
        db.session.add(Offering(canvas_id=404, key="404", name="CS 10 - LEC 001", code="CS 10"))
        self.staff.canvas_courses = {**self.staff.canvas_courses,
                                     "404": {**canvas_course("CS 10", staff=True), "start_at": None}}
        db.session.commit()
        page = self.get("/offerings").get_data(as_text=True)
        self.assertIn('<small class="offering-term">No Date</small>', page)
        self.assertIn('<small class="offering-term">2026-08</small>', page)

    def test_offerings_pages_nav_and_import_button(self):
        page = self.get("/offerings").get_data(as_text=True)
        self.assertNotIn(">Home<", page)
        self.assertNotIn(">Offerings</a>", page)  # already on it
        page = self.get("/offerings/new").get_data(as_text=True)
        self.assertIn('href="/offerings">Offerings</a>', page)
        self.assertIn('value="Import"', page)
