"""Templates used to be named *.html.j2, which Flask does not autoescape, so Canvas course names and
user names were rendered as raw HTML. They are named *.html now, which Flask escapes by default; these
tests make sure they stay escaped."""

import os
import unittest

from application import TEMPLATES_DIR
from models import Offering, User, db
from tests.unit.support import AppTestCase

NAME = '<script>alert("x")</script> & co'
ESCAPED_NAME = "&lt;script&gt;alert(&#34;x&#34;)&lt;/script&gt; &amp; co"

# Templates that are deliberately not HTML, and so not escaped (none yet).
NOT_HTML_TEMPLATES = set()


class AutoescapeTests(AppTestCase):
    def setUp(self):
        super().setUp()
        course = {"name": NAME, "code": NAME, "start_at": "2026-08-19T07:00:00Z",
                  "is_staff": True, "is_admin": False, "is_student": False}
        db.session.add(Offering(canvas_id=101, key="101", name=NAME, code=NAME, start_at=course["start_at"]))
        user = User(email="staff@test", name=NAME, canvas_id="1",
                    canvas_courses={"101": course, "202": course})
        db.session.add(user)
        db.session.commit()
        self.sign_in(user)

    def test_autoescape_follows_flasks_rule(self):
        # Flask escapes templates whose name ends in .html, .htm, .xml, .xhtml or .svg.
        for filename, escaped in [
            ("landing.html", True),
            ("feed.xml", True),
            ("email.txt", False),
            ("landing.html.j2", False),  # why templates are named by their real extension
            (None, True),  # render_template_string
        ]:
            with self.subTest(filename=filename):
                self.assertIs(self.app.select_jinja_autoescape(filename), escaped)

    def test_every_template_is_autoescaped(self):
        # An HTML template named so that Flask does not escape it (say foo.j2 or foo.html.j2) would
        # print Canvas data as raw HTML: name it *.html, or list it in NOT_HTML_TEMPLATES if it is not HTML.
        templates = sorted(os.listdir(TEMPLATES_DIR))
        self.assertTrue(templates)
        not_escaped = {t for t in templates if not self.app.select_jinja_autoescape(t)}
        self.assertEqual(not_escaped, NOT_HTML_TEMPLATES)

    def test_no_template_is_shadowed_by_the_react_build(self):
        # main.py looks in the React build (static/) first, so its index.html would win.
        self.assertNotIn("index.html", os.listdir(TEMPLATES_DIR))

    def test_canvas_and_user_names_are_escaped(self):
        for path in ["/offerings", "/offerings/new"]:
            with self.subTest(path=path):
                page = self.client.get(path).get_data(as_text=True)
                self.assertIn(ESCAPED_NAME, page)
                self.assertNotIn("<script>alert", page)


if __name__ == "__main__":
    unittest.main()
