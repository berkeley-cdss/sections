"""Signing in and out, and setting up a course from Canvas."""

from server.models import Offering
from tests.browser import OFFERING, STUDENT


def test_staff_import_a_course_from_canvas(site, database):
    # Jimmy Xu is a student in the seeded course and a TA in COMPSCI 168, which isn't set up yet.
    site.visit("/offerings", STUDENT)
    site.click("Import courses from Canvas")
    site.find('//label[contains(., "COMPSCI 168")]').click()
    site.find('//input[@type="submit"][@value="Import"]').click()

    site.wait(lambda: site.has_text("Imported 1 course offerings."))
    site.find('//a[contains(@class, "item-link")][contains(., "Introduction to the Internet")]').click()
    site.settle()
    assert site.driver.current_url == f"{site.base_url}/offerings/2345678/"
    assert site.has_text("COMPSCI 168 Sections")
    with database() as session:
        assert session.query(Offering).filter_by(canvas_id=2345678).one().code == "COMPSCI 168"


def test_signing_out_and_back_in(site):
    site.visit(f"{OFFERING}/", STUDENT)
    site.button("Jimmy Xu").click()
    site.button("Log out").click()
    site.wait(lambda: site.driver.current_url == f"{site.base_url}/")

    # Signed out, the course page asks to sign in, and signing in comes back to it.
    site.visit(f"{OFFERING}/lab")
    assert site.has_text("Sign in to see lab sections.")
    assert not site.has_text("has not yet set up")
    site.button("Sign in").click()
    site.wait(lambda: site.driver.current_url.startswith(f"{site.base_url}/dev_login/"))
    site.find(f'//button[@name="user_id"][@value="{STUDENT}"]').click()
    site.wait(lambda: site.driver.current_url == f"{site.base_url}{OFFERING}/lab")
    site.settle()
    assert site.has_text("You have enrolled in")
