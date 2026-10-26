import os
import tempfile
import unittest

import sqlalchemy as sa
from flask import Flask
from flask_migrate import Migrate, upgrade

from models import db

MIGRATIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")


class SingleUserMigrationTests(unittest.TestCase):
    """0002_single_user merges per-offering user rows into one user per person."""

    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{self.path}"
        db.init_app(self.app)
        Migrate(self.app, db, directory=MIGRATIONS)
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        os.remove(self.path)

    def sql(self, statement, **params):
        with db.engine.begin() as conn:
            return conn.execute(sa.text(statement), params).all() if statement.lstrip().upper().startswith("SELECT") \
                else conn.execute(sa.text(statement), params)

    def test_merges_people_and_repoints_references(self):
        upgrade(revision="0001_baseline")
        self.sql("""INSERT INTO "user" (id, course, email, name, is_staff, is_admin) VALUES
            (10, 'cs61a', 'ada@test', 'Ada', 0, 0),
            (11, 'data8', 'ada@test', 'Ada L.', 1, 1),
            (12, 'cs61a', 'tutor@test', 'Tutor', 1, 0),
            (13, 'eecs16b', 'bob@test', 'Bob', NULL, NULL)""")
        self.sql("""INSERT INTO account (id, canvas_id, email, name, is_global_admin, canvas_courses)
            VALUES (1, '555', 'ada@test', 'Ada Lovelace', 0, '{"101": {"is_staff": false}}'),
                   (2, '556', 'new@test', 'Only Logged In', 1, '{}')""")
        self.sql("""INSERT INTO section (id, course, staff_id, tag_string, location, name) VALUES
            (1, 'cs61a', 12, '', 'Soda', 'Lab'), (2, 'data8', 11, '', 'Evans', 'Lab')""")
        self.sql("INSERT INTO user_section (user_id, section_id) VALUES (10, 1), (13, 1)")
        self.sql("INSERT INTO session (id, course, start_time, section_id) VALUES (1, 'cs61a', 0, 1)")
        self.sql("""INSERT INTO attendance (id, course, status, session_id, student_id)
            VALUES (1, 'cs61a', 'present', 1, 10)""")
        self.sql("INSERT INTO offerings (id, canvas_id, key, name) VALUES (1, 101, 'cs61a', 'CS 61A')")
        self.sql("CREATE TABLE course (id INTEGER PRIMARY KEY)")
        self.sql("CREATE TABLE slot (id INTEGER PRIMARY KEY)")
        # Monorepo databases link sessions to slots.
        self.sql("ALTER TABLE session ADD COLUMN slot_id INTEGER REFERENCES slot(id)")
        self.sql("CREATE TABLE survey (id INTEGER PRIMARY KEY)")
        self.sql("CREATE TABLE user_section_junction (user_id INTEGER REFERENCES \"user\"(id), section_id INTEGER)")

        upgrade()

        self.assertNotIn("slot_id", {c["name"] for c in sa.inspect(db.engine).get_columns("session")})
        tables = set(sa.inspect(db.engine).get_table_names())
        self.assertIn("users", tables)
        for gone in ("user", "account", "course", "slot", "survey", "user_section_junction", "user_id_map"):
            self.assertNotIn(gone, tables)

        people = {row.email: row for row in self.sql("SELECT * FROM users")}
        self.assertEqual(set(people), {"ada@test", "tutor@test", "bob@test", "new@test"})
        ada = people["ada@test"]
        # Logged-in people keep their Canvas name and details.
        self.assertEqual((ada.name, ada.canvas_id), ("Ada Lovelace", "555"))
        self.assertEqual(
            (ada.student_offerings, ada.staff_offerings, ada.admin_offerings), ("cs61a", "data8", "data8"))
        self.assertEqual(people["bob@test"].student_offerings, "eecs16b")  # unknown role counts as student
        self.assertTrue(people["new@test"].is_global_admin)

        # Every reference now points at the merged person.
        ids = {email: row.id for email, row in people.items()}
        self.assertEqual(self.sql("SELECT staff_id FROM section ORDER BY id"),
                         [(ids["tutor@test"],), (ids["ada@test"],)])
        self.assertEqual(sorted(self.sql("SELECT user_id FROM user_section")),
                         sorted([(ids["ada@test"],), (ids["bob@test"],)]))
        self.assertEqual(self.sql("SELECT student_id FROM attendance"), [(ids["ada@test"],)])
        foreign_keys = {
            (table, fk["referred_table"])
            for table in ("attendance", "section", "user_section")
            for fk in sa.inspect(db.engine).get_foreign_keys(table)
        }
        self.assertIn(("attendance", "users"), foreign_keys)
        self.assertIn(("section", "users"), foreign_keys)
        self.assertIn(("user_section", "users"), foreign_keys)
        self.assertNotIn("user", {referred for _, referred in foreign_keys})

    def test_fresh_database(self):
        upgrade()
        self.assertEqual(self.sql("SELECT count(*) FROM users"), [(0,)])


if __name__ == "__main__":
    unittest.main()
