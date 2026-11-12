"""A course admin changing the course's settings, and what students see as a result."""

import json
import urllib.error
import urllib.request

from selenium.webdriver.common.by import By

from server.models import CourseConfig, Section, User
from tests.browser import COURSE, LAB_ID, OFFERING, STUDENT, TEACHER


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


def students(database):
    with database() as session:
        return {user.email for user in session.query(User).all() if str(COURSE) in user.student_offerings}


def test_admin_syncs_students_with_bcourses(site, database):
    # Dropped from the course in bCourses since being put in the lab.
    with database() as session:
        dropped = User(email="dropped@example.com", name="Dropped")
        dropped.set_role(str(COURSE), is_staff=False)
        dropped.sections.append(session.get(Section, LAB_ID))
        session.add(dropped)
        session.commit()

    site.visit(f"{OFFERING}/admin", TEACHER)
    site.click("Roster Management", site.find('//*[@role="tablist"]'))
    site.click("Sync bCourses Students")
    dialog = site.find('//*[@role="dialog"]')
    # The fake Canvas lists three students in the course; Jimmy Xu is already here.
    site.wait(lambda: "This will add 2 and remove 1 students." in dialog.text)
    assert students(database) == {"jimmyxu@example.com", "dropped@example.com"}

    site.click("Sync", dialog)
    site.wait(lambda: site.has_text("Added 2 students and removed 1."))
    assert students(database) == {"jimmyxu@example.com", "sharon@berkeley.edu", "angelaz8@berkeley.edu"}
    with database() as session:
        assert [user.email for user in session.get(Section, LAB_ID).students] == ["jimmyxu@example.com"]


def test_students_cannot_open_the_admin_page(site):
    site.visit(f"{OFFERING}/", STUDENT)
    assert not site.has_text("Admin")

    driver = site.visit(f"{OFFERING}/admin", STUDENT)
    site.wait(lambda: driver.current_url.rstrip("/") == f"{site.base_url}{OFFERING}")
    assert not site.has_text("Admin Settings")


def call_api(site, key, method, **body):
    request = urllib.request.Request(
        f"{site.base_url}{OFFERING}/api/sudo/{method}", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        with error:
            return error.code, json.load(error)


def test_admin_makes_uses_rotates_and_revokes_an_api_key(site):
    site.visit(f"{OFFERING}/admin", TEACHER)
    site.click("API Keys", site.find('//*[@role="tablist"]'))
    site.find('//input[@id="api-key-name"]').send_keys("Attendance sync")
    site.click("Create key")
    key = site.find('//input[@aria-label="New API key"]').get_attribute("value")
    assert key.startswith("sections_")
    row = site.find('//tr[contains(., "Attendance sync")]')
    assert f"…{key[-4:]}" in row.text and "You" in row.text

    status, body = call_api(site, key, "refresh_state")
    assert status == 200 and body["data"]["currentUser"]["isAdmin"] is True

    site.click("Rotate", row)
    site.wait(lambda: site.find('//input[@aria-label="New API key"]').get_attribute("value") != key)
    new_key = site.find('//input[@aria-label="New API key"]').get_attribute("value")
    assert site.has_text("Your new key for “Attendance sync”")
    row = site.find('//tr[contains(., "Attendance sync")]')
    assert f"…{new_key[-4:]}" in row.text
    assert len(site.driver.find_elements(By.XPATH, '//tr[contains(., "Attendance sync")]')) == 1  # old key gone
    assert call_api(site, key, "refresh_state")[0] == 401
    assert call_api(site, new_key, "refresh_state")[0] == 200

    site.button("Revoke", row).click()  # not site.click, which can't wait behind the confirm dialog
    site.driver.switch_to.alert.accept()
    site.settle()
    site.wait(lambda: site.has_text("No one has an API key for this course."))
    status, body = call_api(site, new_key, "refresh_state")
    assert status == 401


def test_admin_finds_a_students_sections(site):
    site.visit(f"{OFFERING}/admin", TEACHER)
    site.click("Roster Management", site.find('//*[@role="tablist"]'))
    field = site.find('//input[@id="student-search"]')
    field.send_keys("jimmy")
    site.click("Search", field.find_element(By.XPATH, ".."))
    site.wait(lambda: site.has_text("jimmyxu@example.com"))
    row = site.find('//tr[contains(., "jimmyxu@example.com")]')
    # In Yu Long's lab, and in no discussion yet.
    assert "Lab: Yu Long" in row.text
    assert "Soda 271" in row.text
    assert "Discussion: Floating" in row.text
    assert "Tutoring" not in row.text

    field.clear()
    field.send_keys("nobody")
    site.click("Search", field.find_element(By.XPATH, ".."))
    site.wait(lambda: site.has_text("No students match “nobody”."))
