"""Per-person API keys, scoped to the courses their owner is an admin in (#29)."""

import time

from server.api_keys import hash_key
from server.models import ApiKey, User, db
from tests.unit.support import CS61A, DATA8, CourseTestCase, canvas_course


class ApiKeyTests(CourseTestCase):
    def setUp(self):
        super().setUp()
        self.make_staff_admin()
        self.mark_synced(self.staff_id)

    def mark_synced(self, user_id, ago=0):
        user = db.session.get(User, user_id)
        user.canvas_synced_at = int(time.time()) - ago
        db.session.commit()

    def create_key(self, name="Grading script"):
        body = self.api("create_api_key", name=name).get_json()
        self.assertTrue(body["success"], body)
        return body["data"]["key"]

    def sudo(self, method, key, canvas_course_id=CS61A, **body):
        headers = {"Authorization": f"Bearer {key}"} if key is not None else {}
        return self.post(f"/offerings/{canvas_course_id}/api/sudo/{method}", json=body, headers=headers)

    def test_admins_create_keys_shown_once_and_stored_hashed(self):
        body = self.api("create_api_key", name="  Grading script ").get_json()["data"]
        key = body["key"]
        self.assertTrue(key.startswith("sections_"))
        [listed] = body["keys"]
        self.assertEqual((listed["name"], listed["hint"], listed["owner"]["email"], listed["isMine"]),
                         ("Grading script", key[-4:], "staff@test", True))
        self.assertNotIn("key", listed)
        stored = ApiKey.query.one()
        self.assertEqual(stored.key_hash, hash_key(key))
        self.assertEqual(self.api("list_api_keys").get_json()["data"], body["keys"])
        self.assertFalse(self.api("create_api_key", name=" ").get_json()["success"])

    def test_a_key_acts_as_its_owner_or_a_member_of_the_course(self):
        key = self.create_key()
        with self.assertLogs("sections.api_keys", "INFO") as logs:
            body = self.sudo("export_rosters", key, args={}).get_json()
        self.assertTrue(body["success"], body)
        self.assertIn("called export_rosters as staff@test", logs.output[0])
        self.assertIsNotNone(ApiKey.query.one().last_used_at)

        body = self.sudo("refresh_state", key, email="known@test").get_json()
        self.assertEqual(body["data"]["currentUser"]["email"], "known@test")

        # Someone only in another course can't be acted as.
        outsider = User(email="outsider@test", name="Outsider")
        outsider.set_role(str(DATA8), is_staff=True, is_admin=True)
        db.session.add(outsider)
        db.session.commit()
        response = self.sudo("refresh_state", key, email="outsider@test")
        self.assertEqual(response.status_code, 404)

    def test_a_key_works_only_in_its_own_course(self):
        key = self.create_key()
        response = self.sudo("refresh_state", key, canvas_course_id=DATA8)
        self.assertEqual(response.status_code, 401)
        self.assertIn("isn't valid for this course", response.get_json()["message"])

    def test_missing_or_wrong_keys_are_refused(self):
        self.create_key()
        for key in (None, "", "sections_wrong"):
            with self.subTest(key=key):
                response = self.sudo("refresh_state", key)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn("signed out", response.get_json()["message"])

    def test_the_shared_secret_endpoints_are_gone(self):
        response = self.post(f"/offerings/{CS61A}/api/sudo/refresh_state",
                             json={"secret": "x", "email": "staff@test", "args": {}})
        self.assertEqual(response.status_code, 401)
        self.assertIn(self.api("export_attendance_secret", secret="x").status_code, (404, 405))

    def test_keys_stop_working_when_the_owners_roles_are_stale(self):
        key = self.create_key()
        self.mark_synced(self.staff_id, ago=8 * 24 * 60 * 60)
        response = self.sudo("refresh_state", key)
        self.assertEqual(response.status_code, 403)
        self.assertIn("needs to sign in to Sections again", response.get_json()["message"])
        # Signing in again starts it working.
        self.log_in_as("1", "staff@test", courses={str(CS61A): canvas_course("CS 61A", staff=True, admin=True)})
        self.assertEqual(self.sudo("refresh_state", key).status_code, 200)

    def test_keys_stop_working_when_the_owner_is_no_longer_an_admin(self):
        key = self.create_key()
        self.log_in_as("1", "staff@test", courses={str(CS61A): canvas_course("CS 61A", staff=True)})
        response = self.sudo("refresh_state", key)
        self.assertEqual(response.status_code, 403)
        self.assertIn("no longer an admin", response.get_json()["message"])

    def test_revoking_and_rotating(self):
        key = self.create_key()
        key_id = ApiKey.query.one().id
        body = self.api("rotate_api_key", key_id=str(key_id)).get_json()["data"]
        new_key = body["key"]
        self.assertEqual([k["name"] for k in body["keys"]], ["Grading script"])
        self.assertEqual(self.sudo("refresh_state", key).status_code, 401)
        self.assertEqual(self.sudo("refresh_state", new_key).status_code, 200)

        new_id = body["keys"][0]["id"]
        self.assertEqual(self.api("revoke_api_key", key_id=str(new_id)).get_json()["data"], [])
        self.assertEqual(self.sudo("refresh_state", new_key).status_code, 401)
        self.assertFalse(self.api("revoke_api_key", key_id=str(new_id)).get_json()["success"])

    def test_admins_revoke_but_cannot_rotate_others_keys(self):
        other = User(email="other-admin@test", name="Other", canvas_id="30",
                     canvas_courses={str(CS61A): canvas_course("CS 61A", staff=True, admin=True)})
        other.set_role("cs61a", is_staff=True, is_admin=True)
        db.session.add(other)
        db.session.commit()
        self.sign_in(other)
        self.create_key("Theirs")
        key_id = str(ApiKey.query.one().id)
        self.sign_in(db.session.get(User, self.staff_id))
        [listed] = self.api("list_api_keys").get_json()["data"]
        self.assertFalse(listed["isMine"])
        body = self.api("rotate_api_key", key_id=key_id).get_json()
        self.assertIn("only rotate your own", body["message"])
        self.assertTrue(self.api("revoke_api_key", key_id=key_id).get_json()["success"])

    def test_keys_cannot_manage_keys(self):
        key = self.create_key()
        for method, args in (("list_api_keys", {}), ("create_api_key", {"name": "More"}),
                             ("revoke_api_key", {"key_id": str(ApiKey.query.one().id)})):
            with self.subTest(method=method):
                body = self.sudo(method, key, args=args).get_json()
                self.assertFalse(body["success"])
                self.assertIn("can't be done with an API key", body["message"])
        self.assertEqual(ApiKey.query.filter_by(revoked_at=None).count(), 1)

    def test_staff_who_are_not_admins_cannot_manage_keys(self):
        staff = db.session.get(User, self.staff_id)
        staff.canvas_courses = {str(CS61A): canvas_course("CS 61A", staff=True)}
        staff.set_role("cs61a", is_staff=True)
        db.session.commit()
        self.assertFalse(self.api("list_api_keys").get_json()["success"])
        self.assertFalse(self.api("create_api_key", name="x").get_json()["success"])

    def test_repeated_failures_are_rate_limited(self):
        key = self.create_key()
        for _ in range(10):
            self.assertEqual(self.sudo("refresh_state", "sections_guess").status_code, 401)
        response = self.sudo("refresh_state", key)  # even a good key, from the same client
        self.assertEqual(response.status_code, 429)
        # Other clients aren't affected.
        response = self.post(f"/offerings/{CS61A}/api/sudo/refresh_state", json={},
                             headers={"Authorization": f"Bearer {key}"},
                             environ_base={"REMOTE_ADDR": "10.0.0.2"})
        self.assertEqual(response.status_code, 200)

    def fail_from(self, forwarded_for, times=10):
        for _ in range(times):
            response = self.post(f"/offerings/{CS61A}/api/sudo/refresh_state", json={},
                                 headers={"Authorization": "Bearer sections_guess",
                                          "X-Forwarded-For": forwarded_for})
            self.assertEqual(response.status_code, 401)

    def sudo_from(self, key, forwarded_for):
        return self.post(f"/offerings/{CS61A}/api/sudo/refresh_state", json={},
                         headers={"Authorization": f"Bearer {key}", "X-Forwarded-For": forwarded_for})

    def test_reached_directly_clients_are_told_apart_by_the_last_forwarded_address(self):
        key = self.create_key()
        # Cloud Run appends the client's address; the spoofed entries before it vary.
        self.fail_from("1.1.1.1, 203.0.113.1")
        self.assertEqual(self.sudo_from(key, "9.9.9.9, 203.0.113.1").status_code, 429)
        self.assertEqual(self.sudo_from(key, "203.0.113.2").status_code, 200)

    def test_behind_a_load_balancer_clients_are_told_apart_by_the_entry_before_it(self):
        self.app.config["TRUSTED_PROXY_HOPS"] = 1
        key = self.create_key()
        # Every request ends with the load balancer's address, 198.51.100.1.
        self.fail_from("1.1.1.1, 203.0.113.1, 198.51.100.1")
        self.assertEqual(self.sudo_from(key, "9.9.9.9, 203.0.113.1, 198.51.100.1").status_code, 429)
        self.assertEqual(self.sudo_from(key, "203.0.113.2, 198.51.100.1").status_code, 200)

    def test_signing_in_records_when_roles_were_read(self):
        before = int(time.time())
        self.log_in_as("1", "staff@test", courses={str(CS61A): canvas_course("CS 61A", staff=True)})
        db.session.remove()
        self.assertGreaterEqual(db.session.get(User, self.staff_id).canvas_synced_at, before)
