"""Signing in to the fake Canvas, as seating's /dev_login/ does. Only available
while canvas_service.is_mock_canvas(), so never in staging or production."""

import flask
from flask import flash, redirect, render_template, request, url_for

import canvas_service
from fake_canvas_data import FAKE_COURSES, FAKE_ENROLLMENTS, FAKE_USERS
from login import finish_login


def mock_user_roster():
    """The seed users, with the courses they are enrolled in, so that whoever is
    running a dev server can tell the staff accounts from the student ones
    without reading the fixtures."""
    roster = []
    for user_id, user in FAKE_USERS.items():
        courses = []
        for course_id, enrollment in FAKE_ENROLLMENTS.get(user_id, {}).items():
            course = FAKE_COURSES.get(course_id, {})
            roles = sorted({e["type"] for e in enrollment.get("enrollments", [])})
            courses.append({"name": course.get("name", course_id), "roles": roles})
        roster.append({
            "id": user_id,
            "name": user["name"],
            "email": user.get("email", ""),
            "courses": sorted(courses, key=lambda c: c["name"]),
        })
    return sorted(roster, key=lambda u: u["name"])


def create_dev_login_page(app: flask.Flask):
    @app.route("/dev_login/", methods=["GET", "POST"])
    def dev_login():
        if not canvas_service.is_mock_canvas():
            return redirect(url_for("index"))
        if request.method == "POST":
            # A pasted Canvas ID usually arrives with whitespace around it.
            user_id = request.form.get("user_id", "").strip()
            if not user_id:
                flash("Enter a Canvas ID.", "error")
            # The fake Canvas only knows the seeded users, so anything else
            # would fail later on with a stack trace instead of an explanation.
            elif user_id not in FAKE_USERS:
                flash(f"No seeded user has Canvas ID {user_id}. Pick one of the users below.", "error")
            else:
                # What Canvas's token endpoint returns, as seating's fake one does.
                return finish_login({
                    "access_token": "dev_access_token",
                    "token_type": "Bearer",
                    "user": FAKE_USERS[user_id],
                    "expires_in": 3600,
                })
        return render_template("dev_login.html", title="Dev Login", mock_users=mock_user_roster())
