"""Landing page and course offering pages, matching seating's routes and layout."""

import click
import flask
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import Course, db


def _categorized_offerings(account):
    """Set-up courses the account is staff in, a student in, or otherwise
    enrolled in, like seating's offerings page."""
    canvas_ids = [int(i) for i in account.canvas_courses]
    existing = Course.query.filter(Course.canvas_id.in_(canvas_ids)).all()
    staff, students, other = [], [], []
    for course in existing:
        info = account.canvas_courses[str(course.canvas_id)]
        # Courses linked from the monorepo start without Canvas details.
        if course.code is None:
            course.name, course.code, course.start_at = info["name"], info["code"], info["start_at"]
        if info["is_staff"] or account.is_global_admin:
            staff.append(course)
        elif info["is_student"]:
            students.append(course)
        else:
            other.append(course)
    if account.is_global_admin:
        staff += Course.query.filter(Course.canvas_id.notin_(canvas_ids)).all()
    db.session.commit()

    def newest_first(courses):
        return sorted(courses, key=lambda c: (c.start_at or "", c.display_name), reverse=True)

    return newest_first(staff), newest_first(students), newest_first(other)


def create_course_list(app: flask.Flask):
    # Stylesheets and scripts for the server-rendered pages (static/ holds the React build).
    app.register_blueprint(Blueprint("pages", __name__, static_folder="assets", static_url_path="/assets"))

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("offerings"))
        return render_template("index.html.j2", title="Sections")

    @app.route("/offerings")
    @login_required
    def offerings():
        staff, students, other = _categorized_offerings(current_user)
        return render_template(
            "select_offering.html.j2",
            title="Select a Course Offering",
            staff_offerings_existing=staff,
            student_offerings_existing=students,
            other_offerings_existing=other,
        )

    @app.route("/offerings/new", methods=["GET", "POST"])
    @login_required
    def add_offerings():
        existing = {c.canvas_id for c in Course.query.with_entities(Course.canvas_id)}
        candidates = {
            int(canvas_id): info
            for canvas_id, info in current_user.canvas_courses.items()
            if info["is_staff"] and int(canvas_id) not in existing
        }
        if not candidates:
            flash("No more new courses to import.", "info")
            return redirect(url_for("offerings"))
        if request.method == "POST":
            chosen = [int(i) for i in request.form.getlist("offerings") if i.isdigit() and int(i) in candidates]
            if not chosen:
                flash("No course offering imported.", "info")
                return redirect(url_for("offerings"))
            db.session.add_all(
                Course(canvas_id=i, key=str(i), name=candidates[i]["name"],
                       code=candidates[i]["code"], start_at=candidates[i]["start_at"])
                for i in chosen
            )
            db.session.commit()
            flash(f"Imported {len(chosen)} course offerings.", "success")
            return redirect(url_for("offerings"))
        rows = sorted(candidates.items(), key=lambda item: (item[1]["start_at"] or "", item[1]["name"]), reverse=True)
        return render_template("new_offerings.html.j2", title="Add New Course Offerings", candidates=rows)

    @app.cli.command("link-course")
    @click.argument("canvas_id", type=int)
    @click.argument("key")
    @click.argument("name")
    def link_course(canvas_id, key, name):
        """Set up CANVAS_ID using existing data stored under KEY (e.g. cs61a).

        NAME is shown until a course member signs in, which fills in the
        course's Canvas name, code and start date.
        """
        if Course.query.filter((Course.canvas_id == canvas_id) | (Course.key == key)).first():
            raise click.ClickException(f"Canvas course {canvas_id} or key '{key}' is already linked.")
        db.session.add(Course(canvas_id=canvas_id, key=key, name=name))
        db.session.commit()
        click.echo(f"Linked Canvas course {canvas_id} to '{key}' as {name}.")

    @app.cli.command("set-slack-webhook")
    @click.argument("canvas_id", type=int)
    @click.argument("url")
    def set_slack_webhook(canvas_id, url):
        """Set the Slack incoming webhook URL for CANVAS_ID."""
        course = Course.query.filter_by(canvas_id=canvas_id).one_or_none()
        if course is None:
            raise click.ClickException("That Canvas course isn't set up.")
        course.slack_webhook_url = url
        db.session.commit()
        click.echo(f"Updated the Slack webhook for {course.display_name}.")
