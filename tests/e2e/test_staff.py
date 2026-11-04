"""Staff taking attendance and managing a section's roster."""

from server.models import Attendance, AttendanceStatus, Section, Session, User
from tests.browser import LAB_ID, OFFERING, STUDENT, STUDENT_ID, TA, TEACHER


def attendance_of(database, student_id=STUDENT_ID):
    with database():
        rows = (Attendance.query.filter_by(student_id=student_id).join(Session)
                .order_by(Session.start_time).all())
        return [row.status for row in rows]


def test_ta_takes_attendance_and_the_student_sees_it(site, database):
    site.visit(f"{OFFERING}/section/{LAB_ID}", TA)
    site.click("Start Session")
    site.wait(lambda: not site.has_text("(not started)"))
    # the new session's card comes first, above the seeded one
    site.click("Present", site.card("Jimmy Xu"))
    site.wait(lambda: "btn-success" in site.button("Present", site.card("Jimmy Xu")).get_attribute("class"))
    site.wait(lambda: attendance_of(database) == [AttendanceStatus.present, AttendanceStatus.present])

    site.click("Absent", site.card("Jimmy Xu"))
    site.wait(lambda: attendance_of(database) == [AttendanceStatus.present, AttendanceStatus.absent])

    site.visit(f"{OFFERING}/history", STUDENT)
    rows = site.driver.find_elements("css selector", "table tbody tr")
    statuses = sorted(row.find_element("css selector", ".btn-success, .btn-danger").text for row in rows)
    assert statuses == ["Absent", "Present"]


def test_teacher_adds_and_removes_students_from_the_roster(site, database):
    site.visit(f"{OFFERING}/section/{LAB_ID}", TEACHER)
    site.click("Roster")
    site.card("jimmyxu@example.com")

    # Sharon Lovera is a student in the fake Canvas course, but hasn't signed in to Sections yet.
    site.click("Add Students", site.card("They will be moved here."))
    modal = site.find('//*[contains(@class, "modal-dialog")]')
    modal.find_element("css selector", "input").send_keys("sharon@berkeley.edu")
    site.click("Add Student(s)", modal)
    site.card("sharon@berkeley.edu")

    site.click("Remove", site.card("jimmyxu@example.com"))
    site.wait(lambda: not site.has_text("jimmyxu@example.com"))

    def roster():
        with database() as session:
            return ([student.email for student in session.get(Section, LAB_ID).students],
                    session.get(User, STUDENT_ID).sections)
    site.wait(lambda: roster() == (["sharon@berkeley.edu"], []))
