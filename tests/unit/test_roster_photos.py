"""Student photos from the Cal 1 Card API: who can see them, and when there are none."""

from unittest.mock import patch

import requests

from server.cache import cache_key_photo, cache_store
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

    def test_no_photo_for_an_sid_that_is_not_only_digits(self):
        self.use_real_c1c()
        db.session.get(User, self.known_id).sid = "../3030000000"
        db.session.commit()
        with patch("server.c1c_service.requests.get") as request:
            self.assertEqual(self.get(PHOTO_URL.format(self.known_id)).status_code, 404)
        request.assert_not_called()

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
                               C1C_PROXY_URL="http://proxy.test", C1C_PHOTO_CACHE_LIFE=60)

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
            proxies={"http": "http://proxy.test", "https": "http://proxy.test"}, timeout=(3, 5))

    def test_c1c_errors_and_timeouts_mean_no_photo(self):
        self.use_real_c1c()
        with patch("server.c1c_service.requests.get") as request:
            request.return_value.status_code = 500
            self.assertEqual(self.get(PHOTO_URL.format(self.known_id)).status_code, 404)
            request.side_effect = requests.Timeout()
            self.assertEqual(self.get(PHOTO_URL.format(self.known_id)).status_code, 404)

    def test_c1c_is_asked_once_for_a_photo_shown_twice(self):
        self.use_real_c1c()
        with patch("server.c1c_service.requests.get") as request:
            request.return_value.status_code = 200
            request.return_value.content = b"jpeg"
            self.get(PHOTO_URL.format(self.known_id))
            response = self.get(PHOTO_URL.format(self.known_id))
        self.assertEqual((response.status_code, response.mimetype, response.data),
                         (200, "image/jpeg", b"jpeg"))
        request.assert_called_once()

    def test_c1c_is_asked_again_once_the_photo_is_older_than_its_cache_life(self):
        self.use_real_c1c()
        # cachelib's SimpleCache reads the clock through cachelib.simple.time.
        with patch("server.c1c_service.requests.get") as request, \
                patch("cachelib.simple.time") as clock:
            request.return_value.status_code = 200
            request.return_value.content = b"jpeg"
            clock.return_value = 1000
            self.get(PHOTO_URL.format(self.known_id))
            clock.return_value = 1000 + 59
            self.get(PHOTO_URL.format(self.known_id))
            self.assertEqual(request.call_count, 1)
            clock.return_value = 1000 + 60  # C1C_PHOTO_CACHE_LIFE in use_real_c1c
            self.get(PHOTO_URL.format(self.known_id))
            self.assertEqual(request.call_count, 2)

    def test_c1c_is_asked_again_after_it_had_no_photo(self):
        self.use_real_c1c()
        with patch("server.c1c_service.requests.get") as request:
            request.return_value.status_code = 404
            self.assertEqual(self.get(PHOTO_URL.format(self.known_id)).status_code, 404)
            request.return_value.status_code = 200
            request.return_value.content = b"jpeg"
            self.assertEqual(self.get(PHOTO_URL.format(self.known_id)).data, b"jpeg")
        self.assertEqual(request.call_count, 2)

    def test_made_up_photos_are_not_cached(self):
        self.assertEqual(self.get(PHOTO_URL.format(self.known_id)).status_code, 200)
        self.assertIsNone(cache_store.get(cache_key_photo("3030000000")))

    def test_each_c1c_call_is_logged_with_its_status_and_time(self):
        self.use_real_c1c()
        with patch("server.c1c_service.requests.get") as request, \
                self.assertLogs("sections.c1c", "INFO") as logs:
            request.return_value.status_code = 404
            self.get(PHOTO_URL.format(self.known_id))
            request.return_value.status_code = 200
            request.return_value.content = b"jpeg"
            self.get(PHOTO_URL.format(self.known_id))
        self.assertEqual([record.levelname for record in logs.records], ["INFO", "INFO"])
        self.assertRegex(logs.output[0], r"c1c_photo status=404 ms=\d+\.\d$")
        self.assertRegex(logs.output[1], r"c1c_photo status=200 ms=\d+\.\d$")

    def test_cached_photos_are_not_logged(self):
        self.use_real_c1c()
        with patch("server.c1c_service.requests.get") as request:
            request.return_value.status_code = 200
            request.return_value.content = b"jpeg"
            self.get(PHOTO_URL.format(self.known_id))
            with self.assertNoLogs("sections.c1c"):
                self.get(PHOTO_URL.format(self.known_id))

    def test_c1c_problems_are_logged_as_warnings_without_the_sid(self):
        self.use_real_c1c()
        with patch("server.c1c_service.requests.get") as request, \
                self.assertLogs("sections.c1c", "INFO") as logs:
            request.return_value.status_code = 407
            self.get(PHOTO_URL.format(self.known_id))
            # requests' own error messages include the URL, and so the SID.
            request.side_effect = requests.ReadTimeout("/c1c-api/v1/photo/3030000000 timed out")
            self.get(PHOTO_URL.format(self.known_id))
        self.assertEqual([record.levelname for record in logs.records], ["WARNING", "WARNING"])
        self.assertIn("c1c_photo status=407 ms=", logs.output[0])
        self.assertIn("c1c_photo error=ReadTimeout ms=", logs.output[1])
        self.assertNotIn("3030000000", "\n".join(logs.output))
