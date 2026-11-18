"""Student photos from the Cal 1 Card API: who can see them, and when there are none."""

from unittest.mock import patch

import requests

from server.models import User, db
from tests.unit.support import CS61A, DATA8, CourseTestCase

PHOTO_URL = f"/offerings/{CS61A}/api/students/{{}}/photo"


class RosterPhotoTests(CourseTestCase):
    config = {"MOCK_C1C": True}

    def setUp(self):
        super().setUp()
        db.session.get(User, self.known_id).sid = "3030000000"
        db.session.commit()

    def test_staff_get_the_photo_and_shared_caches_may_not_keep_it(self):
        response = self.get(PHOTO_URL.format(self.known_id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/svg+xml")
        self.assertEqual(response.headers["Cache-Control"], "private, max-age=3600")

    def test_students_cannot_see_photos(self):
        self.sign_in(self.known)
        self.assertEqual(self.get(PHOTO_URL.format(self.known_id)).status_code, 403)

    def test_signed_out_requests_get_401(self):
        self.client.delete_cookie("session")
        self.assertEqual(self.get(PHOTO_URL.format(self.known_id)).status_code, 401)

    def test_no_photo_without_an_sid(self):
        db.session.get(User, self.known_id).sid = None
        db.session.commit()
        self.assertEqual(self.get(PHOTO_URL.format(self.known_id)).status_code, 404)

    def test_no_photo_of_someone_outside_the_course(self):
        outsider = User(email="outsider@test", name="Outsider", sid="3039999999")
        outsider.set_role(str(DATA8), is_staff=False)
        db.session.add(outsider)
        db.session.commit()
        self.assertEqual(self.get(PHOTO_URL.format(outsider.id)).status_code, 404)

    def test_no_photos_without_c1c_settings(self):
        self.app.config["MOCK_C1C"] = False
        with patch("server.c1c_service.requests.get") as request:
            self.assertEqual(self.get(PHOTO_URL.format(self.known_id)).status_code, 404)
        request.assert_not_called()

    def use_real_c1c(self):
        self.app.config.update(MOCK_C1C=False, C1C_API_DOMAIN="https://c1c.test/",
                               C1C_API_USERNAME="user", C1C_API_PASSWORD="password",
                               C1C_PROXY_URL="http://proxy.test")

    def test_real_api_is_asked_through_the_proxy_as_seating_does(self):
        self.use_real_c1c()
        with patch("server.c1c_service.requests.get") as request:
            request.return_value.status_code = 200
            request.return_value.content = b"jpeg"
            response = self.get(PHOTO_URL.format(self.known_id))
        self.assertEqual((response.status_code, response.mimetype, response.data),
                         (200, "image/jpeg", b"jpeg"))
        request.assert_called_once_with(
            "https://c1c.test/c1c-api/v1/photo/3030000000", auth=("user", "password"),
            proxies={"http": "http://proxy.test", "https": "http://proxy.test"}, timeout=10)

    def test_c1c_errors_and_timeouts_mean_no_photo(self):
        self.use_real_c1c()
        with patch("server.c1c_service.requests.get") as request:
            request.return_value.status_code = 500
            self.assertEqual(self.get(PHOTO_URL.format(self.known_id)).status_code, 404)
            request.side_effect = requests.Timeout()
            self.assertEqual(self.get(PHOTO_URL.format(self.known_id)).status_code, 404)
