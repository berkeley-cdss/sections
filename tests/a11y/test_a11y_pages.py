"""
Runs axe on every page of the app, signed in as the kind of user who sees it,
as seating's tests/a11y/test_a11y_pages.py does.

Each page must meet WCAG 2.1 AA. The WCAG 2.2 AA, best-practice and Section 508 checks are
reported too, but are expected failures until the app meets them.
"""

import re
from dataclasses import dataclass

import pytest

from application import create_app
from tests.a11y.conftest import COURSE, LAB_ID, STUDENT, STUDENT_ID, TA, TEACHER, VIOLATIONS_BY_RULE
from tests.a11y.utils import COMPLETE_A11Y_STANDARDS, REQUIRED_A11Y_STANDARDS, assert_no_violations, run_axe, \
    save_report
from tests.unit.support import TEST_CONFIG

OFFERING = f"/offerings/{COURSE}"


@dataclass
class Page:
    name: str
    # the Flask route that serves it; the course pages' routes serve the React app
    rule: str
    path: str
    user: str = None
    # where the page lands, when visiting it redirects
    lands_on: str = None
    # whether it's one of Sections' error pages (errors.py)
    error: bool = False


PAGES = [
    Page("home", "/", "/"),
    Page("dev login", "/dev_login/", "/dev_login/"),

    Page("student offerings", "/offerings", "/offerings", STUDENT),
    Page("student course", "/offerings/<int:canvas_course_id>/", f"{OFFERING}/", STUDENT),
    Page("student history", "/offerings/<int:canvas_course_id>/history/", f"{OFFERING}/history", STUDENT),
    Page("student labs", "/offerings/<int:canvas_course_id>/lab/", f"{OFFERING}/lab", STUDENT),
    Page("student discussions", "/offerings/<int:canvas_course_id>/disc/", f"{OFFERING}/disc", STUDENT),
    Page("student tutoring", "/offerings/<int:canvas_course_id>/tutoring/", f"{OFFERING}/tutoring", STUDENT),
    # The student is also a TA in a course that isn't set up yet, which they can import.
    Page("add offerings", "/offerings/new", "/offerings/new", STUDENT),
    Page("course not set up", "/offerings/<int:canvas_course_id>/", "/offerings/999/", STUDENT, error=True),

    Page("TA course", "/offerings/<int:canvas_course_id>/", f"{OFFERING}/", TA),
    Page("TA section", "/offerings/<int:canvas_course_id>/section/<path:path>", f"{OFFERING}/section/{LAB_ID}", TA),

    Page("offerings", "/offerings", "/offerings", TEACHER),
    Page("course", "/offerings/<int:canvas_course_id>/", f"{OFFERING}/", TEACHER),
    Page("labs", "/offerings/<int:canvas_course_id>/lab/", f"{OFFERING}/lab", TEACHER),
    Page("discussions", "/offerings/<int:canvas_course_id>/disc/", f"{OFFERING}/disc", TEACHER),
    Page("tutoring", "/offerings/<int:canvas_course_id>/tutoring/", f"{OFFERING}/tutoring", TEACHER),
    Page("admin", "/offerings/<int:canvas_course_id>/admin/", f"{OFFERING}/admin", TEACHER),
    Page("section", "/offerings/<int:canvas_course_id>/section/<path:path>", f"{OFFERING}/section/{LAB_ID}", TEACHER),
    Page("student's history", "/offerings/<int:canvas_course_id>/user/<path:path>",
         f"{OFFERING}/user/{STUDENT_ID}", TEACHER),
]

# GET routes that are not audited, and why
SKIPPED_RULES = {
    "/static/<path:filename>": "not a page",
    "/assets/<path:filename>": "not a page",
    "/<path:filename>": "not a page (the React build's files)",
    "/health": "not a page",
    "/offerings/<int:canvas_course_id>/debug": "not a page",
    "/login/": "redirects to the login page",
    "/authorized/": "redirects after login",
    "/logout/": "redirects after logout",
}

# Sections' error pages are titled with their status, e.g. "404 Not Found", or say what failed.
ERROR_TITLES = re.compile(r"\d{3} |Something went wrong|Couldn't sign you in|Database migration needed")


def test_every_page_is_audited():
    app = create_app(TEST_CONFIG)
    get_rules = {rule.rule for rule in app.url_map.iter_rules() if "GET" in rule.methods}
    audited = {page.rule for page in PAGES}
    missing = get_rules - audited - set(SKIPPED_RULES)
    assert not missing, f"Add these to PAGES or SKIPPED_RULES in {__file__}: {sorted(missing)}"
    assert not audited & set(SKIPPED_RULES)


def _audit(a11y_site, page, standards, label):
    driver = a11y_site.visit(page.path, page.user)
    assert driver.current_url == a11y_site.base_url + (page.lands_on or page.path)
    assert bool(ERROR_TITLES.match(driver.title)) == page.error, driver.title
    # the course pages show their own errors when they can't load
    assert "Couldn't load Sections" not in driver.page_source
    assert "Error: Page not found" not in driver.page_source
    report = run_axe(driver, standards)
    save_report(f"{page.name} {label}", report)
    for violation in report["violations"]:
        VIOLATIONS_BY_RULE[f"{violation['id']} ({label})"].add(page.name)
    assert_no_violations(report)


@pytest.mark.parametrize("page", PAGES, ids=[page.name for page in PAGES])
def test_meets_wcag_21_aa(a11y_site, page):
    _audit(a11y_site, page, REQUIRED_A11Y_STANDARDS, "WCAG 2.1 AA")


@pytest.mark.xfail(reason="WCAG 2.2 AA and best practices are not required yet")
@pytest.mark.parametrize("page", PAGES, ids=[page.name for page in PAGES])
def test_meets_wcag_22_aa(a11y_site, page):
    _audit(a11y_site, page, COMPLETE_A11Y_STANDARDS, "WCAG 2.2 AA")
