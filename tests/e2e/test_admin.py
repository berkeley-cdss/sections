"""A course admin changing the course's settings, and what students see as a result."""

from selenium.webdriver.common.by import By

from server.models import CourseConfig
from tests.browser import COURSE, OFFERING, STUDENT, TEACHER


def config(database):
    with database() as session:
        return session.query(CourseConfig).filter_by(course=str(COURSE)).one()


def test_admin_links_the_staff_page_for_everyone(site, database):
    site.visit(f"{OFFERING}/admin", TEACHER)
    field = site.find('//input[@id="staff-url"]')
    field.send_keys("https://cs169a.org/staff/")
    site.click("Save", field.find_element(By.XPATH, ".."))
    site.wait(lambda: site.has_text("Staff page URL saved."))
    assert config(database).staff_url == "https://cs169a.org/staff/"

    site.visit(f"{OFFERING}/", STUDENT)
    staff = site.button("Staff")
    assert staff.get_attribute("href") == "https://cs169a.org/staff/"
    assert staff.get_attribute("target") == "_blank"


def test_admin_stops_students_joining_discussions(site, database):
    site.visit(f"{OFFERING}/admin", TEACHER)
    site.click("Discussion", site.find('//*[@role="tablist"]'))
    row = site.find('//tr[contains(., "Should students be able to enroll in discussion sections?")]')
    row.find_element(By.CSS_SELECTOR, 'input[type="checkbox"]').click()
    site.settle()
    site.wait(lambda: config(database).can_students_join_disc is False)

    site.visit(f"{OFFERING}/disc", STUDENT)
    assert "Wheeler 150" in site.card("Wheeler 150").text
    assert not site.has_text("Join Section")


def test_students_cannot_open_the_admin_page(site):
    site.visit(f"{OFFERING}/", STUDENT)
    assert not site.has_text("Admin")

    driver = site.visit(f"{OFFERING}/admin", STUDENT)
    site.wait(lambda: driver.current_url.rstrip("/") == f"{site.base_url}{OFFERING}")
    assert not site.has_text("Admin Settings")
