import sys
from datetime import datetime, timedelta
from random import choice

from zoneinfo import ZoneInfo

from flask_migrate import upgrade

from main import app
from models import Offering, Section, db, find_or_add_person


def seed(canvas_course_id: int):
    """Fill a development database with demo sections for the given Canvas course."""
    if app.config["APP_ENV"] != "development":
        return
    with app.app_context():
        upgrade()
        if Offering.query.filter_by(canvas_id=canvas_course_id).one_or_none() is None:
            db.session.add(Offering(canvas_id=canvas_course_id, key=str(canvas_course_id), name="Demo 101"))
        course = str(canvas_course_id)
        pst = ZoneInfo("US/Pacific")
        discussions, labs = [], []
        section_count = 100
        for i in range(section_count):
            t = datetime(year=2020, month=8, day=20, hour=i % 10, minute=0, second=0, tzinfo=pst)

            discussion_section = Section(
                course=course,
                description=f"This is the {section_count + i + 1}th demo section.",
                can_self_enroll=True,
                capacity=5,
                name="Discussion",
                start_time=t.timestamp(),
                end_time=(t + timedelta(minutes=30)).timestamp(),
                location="Wheeler 108",
            )

            lab_section = Section(
                course=course,
                description=f"This is the {i + 1}th demo section.",
                can_self_enroll=True,
                capacity=5,
                name="Lab",
                start_time=t.timestamp(),
                end_time=(t + timedelta(minutes=30)).timestamp(),
                location="Soda 275",
            )

            lab_section.tags = ["NPE"]
            discussion_section.tags = ["NPE"]
            labs.append(lab_section)
            discussions.append(discussion_section)
            db.session.add(lab_section)
            db.session.add(discussion_section)

        users = []

        for i in range(section_count * 2):
            discussion = choice(discussions)
            lab = choice(labs)
            user = find_or_add_person(f"gobears{i}@berkeley.edu", f"Oski {i}th of his name")
            user.set_role(course, is_staff=False)
            user.sections = [discussion, lab]
            db.session.add(user)
            users.append(user)

        db.session.commit()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python seed.py <canvas course id>  (e.g. 157 for Mango 101 on the sandbox)")
    seed(int(sys.argv[1]))
