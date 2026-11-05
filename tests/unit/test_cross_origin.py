"""Posts that another site made a signed-in browser send are refused (issue #49),
and posts from Sections' own pages still work."""

from server.models import Offering
from tests.unit.support import CS61A, UNSET_UP, CourseTestCase

# The test client's requests go to http://localhost.
SAME_ORIGIN = "http://localhost"
# Same site, if Sections were served from a berkeley.edu subdomain, so SameSite=Lax cookies are sent.
OTHER_SUBDOMAIN = "https://evil.berkeley.edu"


class CrossOriginTests(CourseTestCase):
    def assert_refused(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertIn("came from another website", response.get_data(as_text=True))

    def test_cross_origin_form_posts_are_refused(self):
        forged = [
            {"Sec-Fetch-Site": "same-site", "Origin": OTHER_SUBDOMAIN},
            {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"},
            # Browsers that send Origin but not Sec-Fetch-Site
            {"Origin": OTHER_SUBDOMAIN},
            {"Origin": "https://localhost"},  # another scheme is another origin
            {"Origin": "null"},  # e.g. from a sandboxed iframe
        ]
        for headers in forged:
            with self.subTest(headers=headers):
                self.assert_refused(self.post(f"/offerings/{CS61A}/remove", headers=headers))
                self.assert_refused(self.post("/offerings/new", data={"offerings": [str(UNSET_UP)]},
                                              headers=headers))
                self.assert_refused(self.post("/dev_login/", data={"user_id": "123456"}, headers=headers))
        self.assertEqual(Offering.query.filter_by(canvas_id=CS61A).count(), 1)
        self.assertEqual(Offering.query.filter_by(canvas_id=UNSET_UP).count(), 0)

    def test_cross_origin_api_calls_are_refused(self):
        response = self.post(f"/offerings/{CS61A}/api/refresh_state", json={},
                             headers={"Sec-Fetch-Site": "same-site", "Origin": OTHER_SUBDOMAIN})
        self.assertEqual(response.status_code, 403)
        self.assertIn("came from another website", response.get_json()["message"])

    def test_same_origin_posts_work(self):
        for headers in [
            {"Sec-Fetch-Site": "same-origin", "Origin": SAME_ORIGIN},
            {"Origin": SAME_ORIGIN},  # browsers that don't send Sec-Fetch-Site, e.g. Safari before 16.4
            # Sec-Fetch-Site decides when it's sent; "none" is a request the user made directly.
            {"Sec-Fetch-Site": "same-origin", "Origin": "https://evil.example"},
            {"Sec-Fetch-Site": "none"},
        ]:
            with self.subTest(headers=headers):
                response = self.post(f"/offerings/{CS61A}/api/refresh_state", json={}, headers=headers)
                self.assertTrue(response.get_json()["success"])
        # The staff member is an admin of CS 70 in Canvas, so can import and then remove it.
        self.post("/offerings/new", data={"offerings": [str(UNSET_UP)]},
                  headers={"Sec-Fetch-Site": "same-origin", "Origin": SAME_ORIGIN})
        self.assertEqual(Offering.query.filter_by(canvas_id=UNSET_UP).count(), 1)
        self.post(f"/offerings/{UNSET_UP}/remove", headers={"Origin": SAME_ORIGIN})
        self.assertEqual(Offering.query.filter_by(canvas_id=UNSET_UP).count(), 0)

    def test_origin_matches_behind_cloud_run(self):
        # Cloud Run terminates TLS and says so in X-Forwarded-Proto, which ProxyFix trusts, so a
        # browser without Sec-Fetch-Site sends an https Origin to what Flask sees as an http request.
        response = self.post(f"/offerings/{CS61A}/api/refresh_state", json={},
                             headers={"X-Forwarded-Proto": "https", "Origin": "https://localhost"})
        self.assertTrue(response.get_json()["success"])

    def test_requests_without_browser_headers_work(self):
        # Not from a browser, so there's no borrowed cookie; e.g. scripts and the unit tests.
        self.assertTrue(self.api("refresh_state").get_json()["success"])

    def test_cross_origin_gets_are_not_refused(self):
        # Links from other sites, e.g. Canvas's redirect back after login, are GETs.
        response = self.get("/offerings", headers={"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"})
        self.assertEqual(response.status_code, 200)
