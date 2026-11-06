"""Staff's Canvas tokens are kept on the server, not in the session cookie, and
signing out revokes them, so a copy of an old cookie can't use one."""

import time
from unittest.mock import patch

import requests
from flask import session

from server import canvas_service
from server.login import complete_login
from server.models import CanvasToken, User, db
from tests.unit.support import CS61A, CourseTestCase, canvas_course

STAFF_COURSES = {str(CS61A): canvas_course("CS 61A", staff=True)}


class CanvasTokenTests(CourseTestCase):
    def lookup_new_student(self):
        with patch("server.state.canvas_service.get_student_from_email", return_value=("555", "New")) as lookup:
            result = self.add_students("new@test")
        return result, lookup

    def sign_in_through_canvas(self, access_token, cookie_handle=None):
        """complete_login as staff@test, from a browser whose cookie holds cookie_handle."""
        with self.app.test_request_context(), \
             patch("server.login.canvas_service.get_profile",
                   return_value={"primary_email": "staff@test", "short_name": "Staff"}), \
             patch("server.login.canvas_service.get_user_courses", return_value=STAFF_COURSES):
            if cookie_handle is not None:
                session["canvas_token_id"] = cookie_handle
            complete_login({"user": {"id": 1}, "access_token": access_token, "expires_in": 3600})

    def test_logout_deletes_and_revokes_the_token(self):
        self.authorize()
        with patch("server.canvas_tokens.canvas_service.revoke_token") as revoke:
            self.post("/logout/")
        revoke.assert_called_once_with("access")
        self.assertEqual(CanvasToken.query.count(), 0)
        with self.client.session_transaction() as browser:
            self.assertNotIn("canvas_token_id", browser)

    def test_a_copy_of_the_cookie_cannot_use_the_token_after_logout(self):
        self.authorize(handle="copied")
        with patch("server.canvas_tokens.canvas_service.revoke_token"):
            self.post("/logout/")
        # Someone replays a copy of the cookie from before the logout.
        self.sign_in(db.session.get(User, self.staff_id))
        with self.client.session_transaction() as browser:
            browser["canvas_token_id"] = "copied"
        result, lookup = self.lookup_new_student()
        self.assertFalse(result["success"])
        self.assertIn("sign in", result["message"])
        lookup.assert_not_called()

    def test_signing_in_again_revokes_the_previous_token(self):
        self.authorize(handle="first")
        with patch("server.canvas_tokens.canvas_service.revoke_token") as revoke:
            self.sign_in_through_canvas("second", cookie_handle="first")
        revoke.assert_called_once_with("access")
        self.assertEqual([t.access_token for t in CanvasToken.query], ["second"])

    def test_a_token_works_only_for_its_owner(self):
        # A handle for someone else's token, in this staff member's cookie.
        self.authorize(user_id=self.known_id)
        result, lookup = self.lookup_new_student()
        self.assertFalse(result["success"])
        lookup.assert_not_called()

    def test_expired_tokens_are_cleared_at_the_next_sign_in(self):
        self.authorize(expires_in=-10, handle="stale")
        self.sign_in_through_canvas("fresh")
        self.assertEqual([t.access_token for t in CanvasToken.query], ["fresh"])

    def test_tokens_left_in_old_cookies_are_dropped(self):
        with self.client.session_transaction() as browser:
            browser["canvas_access_token"] = "from-an-old-cookie"
            browser["canvas_token_expires_at"] = time.time() + 3600
        self.get("/health")
        with self.client.session_transaction() as browser:
            self.assertNotIn("canvas_access_token", browser)
            self.assertNotIn("canvas_token_expires_at", browser)

    def test_revoke_asks_canvas_and_tolerates_failure(self):
        with self.app.test_request_context():
            with patch("server.canvas_service.requests.delete") as delete:
                canvas_service.revoke_token("tok")
            delete.assert_called_once_with("https://canvas.test/login/oauth2/token",
                                           headers={"Authorization": "Bearer tok"}, timeout=5)
            with patch("server.canvas_service.requests.delete", side_effect=requests.ConnectionError("down")):
                canvas_service.revoke_token("tok")  # doesn't raise
            self.app.config.update(MOCK_CANVAS=True, APP_ENV="development")
            with patch("server.canvas_service.requests.delete") as delete:
                canvas_service.revoke_token("tok")
            delete.assert_not_called()
