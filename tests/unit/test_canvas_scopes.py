"""Every request to Canvas, including each later page of a list, has a scope
requested at sign-in. Canvas refuses any other, and a list's later pages can be
at a different URL from its first (see scoped_canvas)."""

from urllib.parse import parse_qs, urlparse

from canvasapi import Canvas
from canvasapi.exceptions import Unauthorized
from flask import g

from server import canvas_service
from server.models import Offering, User, db
from tests.unit.scoped_canvas import ScopedCanvas, person
from tests.unit.support import CS61A, CourseTestCase

# The scopes on the Sections developer key, on bCourses and on its test
# instance. Canvas rejects a sign-in that asks for any other, so add a scope to
# both keys before adding it here and to canvas_service.SCOPES.
DEVELOPER_KEY_SCOPES = {
    "url:GET|/api/v1/users/:id",
    "url:GET|/api/v1/users/:user_id/profile",
    "url:GET|/api/v1/users/:user_id/courses",
    "url:GET|/api/v1/courses/:id",
    "url:GET|/api/v1/courses/:course_id/enrollments",
    "url:GET|/api/v1/courses/:course_id/users",
}

STAFF_ID = 1


def students(count, first_id=1000):
    return [person(first_id + n) for n in range(count)]


def course_as_canvas_lists_it(course_id):
    return {"id": course_id, "name": f"Course {course_id}", "course_code": f"C{course_id}",
            "term": {"start_at": "2026-08-19T07:00:00Z"},
            "enrollments": [{"type": "teacher", "role": "TeacherEnrollment", "enrollment_state": "active"}]}


class ScopedCanvasTestCase(CourseTestCase):
    def canvas(self, scopes=canvas_service.SCOPES, **kwargs) -> ScopedCanvas:
        """Canvas answering canvasapi's requests until the test ends, with CS 61A
        the current course."""
        canvas = ScopedCanvas(scopes, **kwargs)
        answering = canvas.answering_canvasapi()
        answering.__enter__()
        self.addCleanup(answering.__exit__, None, None, None)
        request = self.app.test_request_context()
        request.push()
        self.addCleanup(request.pop)
        g.offering = Offering.query.filter_by(canvas_id=CS61A).one()
        return canvas


class SignInScopeTests(CourseTestCase):
    def test_scopes_are_the_ones_on_the_developer_key(self):
        self.assertEqual(set(canvas_service.SCOPES), DEVELOPER_KEY_SCOPES)
        self.assertEqual(len(canvas_service.SCOPES), len(DEVELOPER_KEY_SCOPES))

    def test_sign_in_asks_canvas_for_exactly_those_scopes(self):
        self.client.get("/logout/")
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 302)
        location = urlparse(response.headers["Location"])
        self.assertEqual(location.path, "/login/oauth2/auth")
        self.assertEqual(set(parse_qs(location.query)["scope"][0].split(" ")), DEVELOPER_KEY_SCOPES)


class RosterTests(ScopedCanvasTestCase):
    def test_a_roster_of_several_pages(self):
        # What bCourses refused: the pages after the first 100 students.
        canvas = self.canvas(people={CS61A: students(250)})
        roster = canvas_service.get_roster("token")
        self.assertEqual([entry["canvas_id"] for entry in roster], [str(1000 + n) for n in range(250)])
        self.assertEqual(canvas.refused, [])
        self.assertEqual(canvas.requested, [f"/api/v1/courses/{CS61A}"] + [f"/api/v1/courses/{CS61A}/users"] * 3)

    def test_a_roster_that_exactly_fills_its_pages(self):
        canvas = self.canvas(people={CS61A: students(200)})
        self.assertEqual(len(canvas_service.get_roster("token")), 200)
        self.assertEqual(canvas.refused, [])
        self.assertEqual(len(canvas.requested), 3)

    def test_a_roster_of_one_page(self):
        canvas = self.canvas(people={CS61A: students(3)})
        self.assertEqual(len(canvas_service.get_roster("token")), 3)
        self.assertEqual(canvas.requested, [f"/api/v1/courses/{CS61A}", f"/api/v1/courses/{CS61A}/users"])

    def test_students_only_active_or_invited_once_each(self):
        self.canvas(people={CS61A: [
            person(5), person(6, state="invited"),
            # Enrolled in a lecture and a lab: two enrollments, one student.
            person(7), person(7),
            person(8, state="completed"), person(9, state="inactive"), person(10, state="rejected"),
            person(11, type="ta"), person(12, type="teacher"), person(13, type="observer"),
        ]})
        self.assertEqual([entry["canvas_id"] for entry in canvas_service.get_roster("token")], ["5", "6", "7"])

    def test_email_and_display_name(self):
        # At Berkeley the login is a CalNet UID, not an email; and Canvas may not share an email.
        self.canvas(people={CS61A: [
            person(5, email="a@test", name="A", short_name="A (display)", login_id="1717117"),
            person(6, email=None, name="B", short_name=""),
        ]})
        self.assertEqual(canvas_service.get_roster("token"), [
            {"canvas_id": "5", "email": "a@test", "name": "A (display)"},
            {"canvas_id": "6", "email": None, "name": "B"},
        ])

    def test_emails_dont_depend_on_the_key_allowing_include_parameters(self):
        self.canvas(people={CS61A: students(2)}, allow_includes=False)
        self.assertEqual([entry["email"] for entry in canvas_service.get_roster("token")],
                         ["p1000@test", "p1001@test"])

    def test_page_links_keep_the_filters(self):
        # Staff sort among the students, so a later page that forgot the
        # filters would include them.
        people = [person(n, type="ta" if n % 2 else "student") for n in range(1, 401)]
        self.canvas(people={CS61A: people})
        roster = canvas_service.get_roster("token")
        self.assertEqual([entry["canvas_id"] for entry in roster], [str(n) for n in range(2, 401, 2)])


class EveryRequestHasAScopeTests(ScopedCanvasTestCase):
    """Each function in canvas_service that reads from Canvas, on lists long
    enough to need several pages."""

    def big_course(self, **kwargs) -> ScopedCanvas:
        people = [*students(250), *(person(n, type="ta") for n in range(2000, 2140)),
                  *(person(n, type="teacher") for n in range(3000, 3005))]
        courses = [course_as_canvas_lists_it(course_id) for course_id in range(5000, 5230)]
        return self.canvas(people={CS61A: people}, user_courses={STAFF_ID: courses}, **kwargs)

    def read_everything(self):
        """Call each function, checking it read to the end of its list."""
        self.assertEqual(canvas_service.get_profile(STAFF_ID, "token")["primary_email"], "p1@test")
        self.assertEqual(len(canvas_service.get_user_courses(STAFF_ID, "token")), 230)
        self.assertEqual(len(canvas_service.get_course_staff("token")), 145)
        self.assertEqual(len(canvas_service.get_roster("token")), 250)
        # The last student, on the last page of enrollments.
        self.assertEqual(canvas_service.get_student_from_email("1001249", "token"), ("1249", "P1249"))
        self.assertIsNone(canvas_service.get_student_from_email("nobody", "token"))

    def test_nothing_is_refused(self):
        canvas = self.big_course()
        self.read_everything()
        self.assertEqual(canvas.refused, [])
        # Several pages of each list were read, not just the first.
        for path, at_least in ((f"/api/v1/users/{STAFF_ID}/courses", 3),
                               (f"/api/v1/courses/{CS61A}/enrollments", 2 + 3 + 3),
                               (f"/api/v1/courses/{CS61A}/users", 3)):
            self.assertGreaterEqual(canvas.requested.count(path), at_least, path)

    def test_every_scope_is_needed(self):
        # A scope nothing uses is access the stored tokens don't need.
        canvas = self.big_course()
        self.read_everything()
        self.assertEqual(canvas.used_scopes(), set(canvas_service.SCOPES))

    def test_each_scope_is_needed_by_some_function(self):
        for missing in canvas_service.SCOPES:
            with self.subTest(missing=missing):
                canvas = self.big_course(scopes=[s for s in canvas_service.SCOPES if s != missing])
                with self.assertRaises(Unauthorized):
                    self.read_everything()
                self.assertTrue(canvas.refused)


class ScopedCanvasTests(ScopedCanvasTestCase):
    """The stand-in refuses what bCourses refused, so the tests above would
    have caught it."""

    SEARCH_USERS_ONLY = [scope.replace("/users", "/search_users") if scope.endswith(":course_id/users") else scope
                         for scope in canvas_service.SCOPES]

    def get_users(self):
        # canvasapi's own method, which requests search_users.
        course = Canvas("https://canvas.test", "token").get_course(CS61A)
        return list(course.get_users(enrollment_type=["student"], per_page=100))

    def test_search_users_alone_reads_a_small_course(self):
        canvas = self.canvas(scopes=self.SEARCH_USERS_ONLY, people={CS61A: students(100)})
        self.assertEqual(len(self.get_users()), 100)
        self.assertEqual(canvas.refused, [])

    def test_search_users_alone_is_refused_the_second_page(self):
        canvas = self.canvas(scopes=self.SEARCH_USERS_ONLY, people={CS61A: students(101)})
        with self.assertRaises(Unauthorized) as refusal:
            self.get_users()
        self.assertIn("Insufficient scopes on access token.", str(refusal.exception))
        self.assertEqual(canvas.refused, [f"/api/v1/courses/{CS61A}/users"])
        self.assertEqual(canvas.requested[-2:], [f"/api/v1/courses/{CS61A}/search_users",
                                                 f"/api/v1/courses/{CS61A}/users"])

    def test_canvasapis_get_users_is_refused_with_sections_scopes(self):
        canvas = self.canvas(people={CS61A: students(1)})
        with self.assertRaises(Unauthorized):
            self.get_users()
        self.assertEqual(canvas.refused, [f"/api/v1/courses/{CS61A}/search_users"])


class SyncOverScopedCanvasTests(CourseTestCase):
    """The sync from the admin's request down to Canvas's responses."""

    def setUp(self):
        super().setUp()
        self.make_staff_admin()
        self.authorize()

    def sync(self, canvas):
        with canvas.answering_canvasapi():
            body = self.api("sync_bcourses").get_json()
        db.session.remove()
        return body

    def test_syncs_a_course_of_several_pages(self):
        canvas = ScopedCanvas(canvas_service.SCOPES, people={CS61A: students(250) + [person(1, type="teacher")]})
        body = self.sync(canvas)
        self.assertTrue(body["success"], body)
        self.assertEqual(canvas.refused, [])
        # "known" isn't on the roster, so is removed.
        self.assertEqual(body["data"]["custom"]["message"], "Added 250 students and removed 1.")
        enrolled = [user for user in User.query.all() if "cs61a" in user.student_offerings]
        self.assertEqual(len(enrolled), 250)

    def test_a_missing_scope_is_logged_as_canvas_put_it(self):
        scopes = [scope for scope in canvas_service.SCOPES if not scope.endswith(":course_id/users")]
        canvas = ScopedCanvas(scopes, people={CS61A: students(3)})
        with self.assertLogs(self.app.logger, "WARNING") as logs:
            body = self.sync(canvas)
        self.assertFalse(body["success"])
        self.assertIn("can't see this course's students", body["message"])
        self.assertIn("Insufficient scopes on access token.", logs.output[0])
        self.assertEqual({user.email for user in User.query.all() if "cs61a" in user.student_offerings},
                         {"known@test"})
