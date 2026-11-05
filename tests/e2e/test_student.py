"""A student joining, switching and leaving sections."""

from server.models import Section, User
from tests.browser import COURSE, DISCUSSION_ID, LAB_ID, OFFERING, STUDENT, STUDENT_ID


def sections_of(database, user_id=STUDENT_ID):
    with database() as session:
        return sorted((s.name, s.location) for s in session.get(User, user_id).sections_in(str(COURSE)))


def test_student_sees_their_lab(site):
    site.visit(f"{OFFERING}/lab", STUDENT)
    card = site.card("You have enrolled in")
    assert "Lab @ Soda 271" in card.text
    assert "Yu Long" in card.text


def test_student_joins_a_discussion(site, database):
    site.visit(f"{OFFERING}/disc", STUDENT)
    site.click("Join Section (30 spots left)", site.card("Wheeler 150"))

    card = site.card("You have enrolled in")
    assert "Discussion @ Wheeler 150" in card.text
    site.wait(lambda: sections_of(database) == [("Discussion", "Wheeler 150"), ("Lab", "Soda 271")])


def test_student_switches_to_another_lab(site, database):
    with database() as session:
        lab = session.get(Section, LAB_ID)
        session.add(Section(course=lab.course, name="Lab", location="Evans 60", description="", capacity=30,
                            can_self_enroll=True, start_time=lab.start_time + 7200, end_time=lab.end_time + 7200))
        session.commit()

    site.visit(f"{OFFERING}/lab", STUDENT)
    site.click("Switch to Section (30 spots left)", site.card("Evans 60"))

    site.wait(lambda: sections_of(database) == [("Lab", "Evans 60")])


def test_student_leaves_their_lab(site, database):
    site.visit(f"{OFFERING}/lab", STUDENT)
    site.click("Leave Section", site.card("You have enrolled in"))

    site.wait(lambda: not site.has_text("You have enrolled in"))
    site.wait(lambda: sections_of(database) == [])


def test_section_with_an_enrollment_code_needs_it(site, database):
    with database() as session:
        session.get(Section, DISCUSSION_ID).enrollment_code = "owl"
        session.commit()

    site.visit(f"{OFFERING}/disc", STUDENT)
    site.button("Join Section (30 spots left)", site.card("Wheeler 150")).click()
    modal = site.find('//*[contains(@class, "modal-dialog")]')
    code = modal.find_element("css selector", "input")
    code.send_keys("wrong")
    site.click("Submit", modal)
    site.wait(lambda: site.has_text("Invalid enrollment code; cannot join section."))
    site.wait(lambda: sections_of(database) == [("Lab", "Soda 271")])

    site.button("Join Section (30 spots left)", site.card("Wheeler 150")).click()
    modal = site.find('//*[contains(@class, "modal-dialog")]')
    code = modal.find_element("css selector", "input")
    code.clear()
    code.send_keys("owl")
    site.click("Submit", modal)
    site.wait(lambda: sections_of(database) == [("Discussion", "Wheeler 150"), ("Lab", "Soda 271")])
