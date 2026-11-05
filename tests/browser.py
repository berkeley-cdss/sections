"""The live server, browser and seed data that the a11y audit (tests/a11y) and the end to end
tests (tests/e2e) share. Everyone signs in through /dev_login/ against the fake Canvas
(server/fake_canvas.py)."""

import re
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from werkzeug.serving import make_server

from server.application import SERVER_DIR, create_app
from server.models import Attendance, AttendanceStatus, CourseConfig, Offering, Section, Session, User, db
from tests.unit.support import TEST_CONFIG, canvas_course

# Seeded in server/fake_canvas_data: Oski Bear teaches the course, Yu Long is a
# TA in it, and Jimmy Xu is a student in it (and a TA in another course, 2345678).
COURSE = 1234567
TEACHER, TA, STUDENT = "567890", "123456", "234567"
# Database ids of the seeded sections and student, for page paths.
LAB_ID, DISCUSSION_ID, TUTORING_ID = 1, 2, 3
STUDENT_ID = 2
OFFERING = f"/offerings/{COURSE}"

# Counts the page's API requests in flight, so tests can wait for the course
# pages' data to load. It runs before the page's own scripts.
COUNT_FETCHES = """
window.pendingFetches = 0;
const fetch = window.fetch;
window.fetch = (...args) => {
  window.pendingFetches++;
  return fetch(...args).finally(() => window.pendingFetches--);
};
"""
LOADED = """
return document.readyState === 'complete' && window.pendingFetches === 0
  && !document.querySelector('.spinner-border');
"""


def slugify(text):
    """text as a file name, for reports and screenshots."""
    return re.sub(r"[^\w.-]+", "-", text).strip("-")


class Site:
    """One browser on one server, signed in as whoever a page needs."""

    def __init__(self, app, driver, base_url):
        self.app = app
        self.driver = driver
        self.base_url = base_url
        self.user = None

    def visit(self, path, user=None):
        if user != self.user:
            # Signing out leaves no session, whoever was signed in.
            self.driver.delete_all_cookies()
            if user is not None:
                self._login(user)
            self.user = user
        self.driver.get(self.base_url + path)
        self.settle()
        return self.driver

    def _login(self, user):
        self.driver.get(f"{self.base_url}/dev_login/")
        self.driver.find_element(By.CSS_SELECTOR, f'button[name="user_id"][value="{user}"]').click()
        self.wait(lambda: self.driver.current_url == f"{self.base_url}/offerings")

    def wait(self, condition, timeout=10):
        """Wait until condition() is truthy, and return what it returned. React may replace
        an element condition() looks at while it runs, so that is retried too."""
        return WebDriverWait(self.driver, timeout, ignored_exceptions=[StaleElementReferenceException]) \
            .until(lambda _: condition())

    def settle(self):
        """Wait until the page has loaded and its API calls have finished."""
        self.wait(lambda: self.driver.execute_script(LOADED))

    def find(self, xpath, within=None):
        """The visible element at xpath (relative to within, if given), once there is one."""
        root = within or self.driver

        def visible():
            return next((e for e in root.find_elements(By.XPATH, xpath) if e.is_displayed()), None)
        return self.wait(visible)

    def button(self, text, within=None):
        return self.find(f'.//*[(self::button or self::a or @role="button") and normalize-space()="{text}"]',
                         within)

    def click(self, text, within=None):
        """Click the button or link labeled text, then wait for any API calls in flight. A call
        may start just after this returns, so wait for what the click should do, too."""
        self.button(text, within).click()
        self.settle()

    def card(self, text):
        """The card that contains text, not counting cards inside other cards (e.g. a section's
        card, not the time and place shown inside it)."""
        card = 'contains(concat(" ", @class, " "), " card ")'
        return self.find(f'//*[{card}][contains(., "{text}")][not(ancestor::*[{card}])]')

    def has_text(self, text):
        return text in self.driver.find_element(By.TAG_NAME, "body").text

    def reset(self):
        """Seed a fresh database, sign out and forget the page's settings (such as its time
        zone), for a test that changes things."""
        self.driver.get(f"{self.base_url}/health")
        self.driver.delete_all_cookies()
        self.driver.execute_script("localStorage.clear(); sessionStorage.clear();")
        self.user = None
        seed(self.app)


def seed(app):
    """The course, with a lab, a discussion and a tutoring section, each run by
    the TA. The student is in the lab and has attended it."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        course = str(COURSE)
        db.session.add_all([
            Offering(canvas_id=COURSE, key=course, name="Introduction to Software Engineering (Fall 2023)",
                     code="CS 169A", start_at="2023-08-23T07:00:00Z"),
            CourseConfig(course=course),
        ])
        # Signing in through the fake Canvas finds these by Canvas ID and updates them.
        ta = User(email="yulong@example.com", name="Yu Long", canvas_id=TA,
                  canvas_courses={course: canvas_course("CS 169A", staff=True)})
        ta.set_role(course, is_staff=True)
        student = User(email="jimmyxu@example.com", name="Jimmy Xu", canvas_id=STUDENT,
                       canvas_courses={course: canvas_course("CS 169A", student=True)})
        student.set_role(course, is_staff=False)
        sections = [
            Section(course=course, name=name, location=location, description="", capacity=30,
                    can_self_enroll=True, start_time=1629734400 + 86400 * day, end_time=1629738000 + 86400 * day,
                    staff=ta)
            for day, (name, location) in enumerate([("Lab", "Soda 271"), ("Discussion", "Wheeler 150"),
                                                    ("Tutoring", "Cory 247")])
        ]
        sections[0].students.append(student)
        db.session.add_all([ta, student, *sections])
        db.session.flush()
        session = Session(course=course, start_time=sections[0].start_time, section_id=sections[0].id)
        db.session.add(session)
        db.session.flush()
        db.session.add(Attendance(course=course, status=AttendanceStatus.present, session_id=session.id,
                                  student_id=student.id))
        db.session.commit()
        assert [s.id for s in sections] == [LAB_ID, DISCUSSION_ID, TUTORING_ID]
        assert student.id == STUDENT_ID
        db.session.remove()


@contextmanager
def live_site():
    """The app, seeded, on a local server, with headless Chrome to visit it."""
    if not (Path(SERVER_DIR) / "static" / "index.html").exists():
        pytest.fail("The course pages need the frontend build in server/static. "
                    "Run `yarn build && cp -R build/. server/static/`, as the Dockerfile does.")

    with tempfile.TemporaryDirectory() as directory:
        app = create_app({**TEST_CONFIG, "MOCK_CANVAS": True,
                          "SQLALCHEMY_DATABASE_URI": f"sqlite:///{directory}/browser.db"})
        seed(app)
        server = make_server("localhost", 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        # a tall window keeps most of each page on screen, since axe skips the contrast of text off screen
        options.add_argument("--window-size=1280,4000")
        driver = webdriver.Chrome(options=options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": COUNT_FETCHES})
        try:
            yield Site(app, driver, f"http://localhost:{server.server_port}")
        finally:
            driver.quit()
            server.shutdown()
            thread.join()
            server.server_close()
            with app.app_context():
                db.engine.dispose()
