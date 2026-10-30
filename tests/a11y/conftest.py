"""The server, browser and seed data the a11y audit shares, as in
seating's tests/a11y/conftest.py. Everyone signs in through /dev_login/ against
the fake Canvas (server/fake_canvas.py)."""

import tempfile
import threading
from collections import defaultdict
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from werkzeug.serving import make_server

from application import SERVER_DIR, create_app
from models import Attendance, AttendanceStatus, CourseConfig, Offering, Section, Session, User, db
from tests.a11y.utils import REPORT_DIR, slugify
from tests.unit.support import TEST_CONFIG, canvas_course

# Seeded in server/fake_canvas_data: Oski Bear teaches the course, Yu Long is a
# TA in it, and Jimmy Xu is a student in it (and a TA in another course, 2345678).
COURSE = 1234567
TEACHER, TA, STUDENT = "567890", "123456", "234567"
# Database ids of the seeded lab and student, for page paths.
LAB_ID, STUDENT_ID = 1, 2

# rule id -> pages that break it, printed at the end of the run
VIOLATIONS_BY_RULE = defaultdict(set)

# Counts the page's API requests in flight, so an a11y audit waits for the course
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


class Site:
    """One browser on one server, shared by every page's a11y audit, signed in as whoever a page needs."""

    def __init__(self, driver, base_url):
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
        WebDriverWait(self.driver, 10).until(lambda d: d.execute_script(LOADED))
        return self.driver

    def _login(self, user):
        self.driver.get(f"{self.base_url}/dev_login/")
        self.driver.find_element(By.CSS_SELECTOR, f'button[name="user_id"][value="{user}"]').click()
        WebDriverWait(self.driver, 10).until(lambda d: d.current_url == f"{self.base_url}/offerings")


def seed(app):
    """The course, with a lab, a discussion and a tutoring section, each run by
    the TA. The student is in the lab and has attended it."""
    with app.app_context():
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
        assert (sections[0].id, student.id) == (LAB_ID, STUDENT_ID)
        db.session.remove()


@pytest.fixture(scope="session")
def a11y_site():
    if not (Path(SERVER_DIR) / "static" / "index.html").exists():
        pytest.fail("The course pages need the frontend build in server/static. "
                    "Run `yarn build && cp -R build/. server/static/`, as the Dockerfile does.")

    with tempfile.TemporaryDirectory() as directory:
        app = create_app({**TEST_CONFIG, "MOCK_CANVAS": True,
                          "SQLALCHEMY_DATABASE_URI": f"sqlite:///{directory}/a11y.db"})
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
            yield Site(driver, f"http://localhost:{server.server_port}")
        finally:
            driver.quit()
            server.shutdown()
            thread.join()
            server.server_close()
            with app.app_context():
                db.engine.dispose()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    site = item.funcargs.get("a11y_site") if hasattr(item, "funcargs") else None
    if report.when == "call" and report.failed and site is not None:
        screenshots = REPORT_DIR / "screenshots"
        screenshots.mkdir(parents=True, exist_ok=True)
        site.driver.save_screenshot(str(screenshots / f"{slugify(item.name)}.png"))


def pytest_terminal_summary(terminalreporter):
    if not VIOLATIONS_BY_RULE:
        return
    terminalreporter.section("accessibility violations by rule")
    for rule, pages in sorted(VIOLATIONS_BY_RULE.items()):
        terminalreporter.write_line(f"{rule} ({len(pages)} pages)")
        for page in sorted(pages):
            terminalreporter.write_line(f"  {page}")
