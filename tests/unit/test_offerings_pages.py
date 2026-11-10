"""The /offerings pages: listing, importing and removing course offerings."""

from server.models import Offering, Section, User, db
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

    def test_courses_with_too_big_ids_are_skipped(self):
        """A course ID saved at an earlier sign-in that's too big for
        offerings.canvas_id doesn't break the offerings page, and course URLs
        with one aren't found."""
        too_big = 30000002702310
        staff = db.session.get(User, self.staff_id)
        staff.canvas_courses = {**staff.canvas_courses,
                                str(too_big): canvas_course("CS 10", staff=True, admin=True)}
        db.session.commit()
        page = self.get("/offerings").get_data(as_text=True)
        self.assertIn(f'href="/offerings/{CS61A}/"', page)
        self.assertNotIn(str(too_big), page)
        self.assertNotIn(str(too_big), self.get("/offerings/new").get_data(as_text=True))
        self.assertEqual(self.get(f"/offerings/{too_big}/").status_code, 404)
        self.assertEqual(self.post(f"/offerings/{too_big}/remove").status_code, 404)

    def make_cs61a_admin(self):
        staff = db.session.get(User, self.staff_id)
        staff.canvas_courses = {**staff.canvas_courses, str(CS61A): canvas_course("CS 61A", staff=True, admin=True)}
        db.session.commit()

    def test_staff_who_arent_admins_cannot_remove_offerings(self):
        # A TA sees the offering but no remove button, and can't post the form.
        page = self.get("/offerings").get_data(as_text=True)
        self.assertIn(f'href="/offerings/{CS61A}/"', page)
        self.assertNotIn(f'action="/offerings/{CS61A}/remove"', page)
        self.assertEqual(self.post(f"/offerings/{CS61A}/remove").status_code, 403)
        self.assertIsNotNone(Offering.query.filter_by(canvas_id=CS61A).one_or_none())

    def test_global_admins_remove_any_offering(self):
        staff = db.session.get(User, self.staff_id)
        staff.is_global_admin = True
        db.session.commit()
        self.assertIn(f'action="/offerings/{DATA8}/remove"', self.get("/offerings").get_data(as_text=True))
        self.post(f"/offerings/{DATA8}/remove")
        self.assertIsNone(Offering.query.filter_by(canvas_id=DATA8).one_or_none())

    def test_admins_remove_offerings_and_keep_their_data(self):
        self.make_cs61a_admin()
        page = self.get("/offerings").get_data(as_text=True)
        self.assertIn(f'action="/offerings/{CS61A}/remove"', page)
        # As in seating, the button is a hide icon whose tooltip says so.
        self.assertIn('aria-label="Hide CS 61A - LEC 001"', page)
        self.assertIn('data-bs-title="Hide"', page)
        self.assertIn('class="bi bi-eye-slash"', page)

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
        # "cs61a". Staff are told to ask a maintainer, and the log has the command.
        with self.assertLogs(self.app.logger, "INFO") as logs:
            response = self.post(f"/offerings/{CS61A}/remove", follow_redirects=True)
        page = response.get_data(as_text=True)
        self.assertIn("Ask a Sections maintainer to restore them.", page)
        self.assertNotIn("flask", page)
        self.assertIn(f"flask --app server.main link-offering {CS61A} cs61a ", "\n".join(logs.output))
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
