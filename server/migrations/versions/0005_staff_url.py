"""Add course_config.staff_url, the course staff page linked in the nav bar (#25).

Revision ID: 0005_staff_url
Revises: 0004_pronouns
Create Date: 2026-11-03

Until now the nav bar linked https://cs61a.org/staff/ for any offering whose
name contains "61A", and nothing for other courses. This stores the link per
offering instead, and gives the 61A offerings that had the link the same URL,
so nothing changes for them when this deploys. Their admins can change or
clear it on the Admin page.
"""
import re

from alembic import op
import sqlalchemy as sa


revision = "0005_staff_url"
down_revision = "0004_pronouns"
branch_labels = None
depends_on = None

CS61A_STAFF_URL = "https://cs61a.org/staff/"
# The test the nav bar used (App.tsx), against the name it showed (Offering.display_name).
IS_61A = re.compile(r"\b61A\b")


def upgrade():
    with op.batch_alter_table("course_config") as batch:
        batch.add_column(sa.Column("staff_url", sa.String(length=1024), nullable=True))

    bind = op.get_bind()
    offerings = bind.execute(sa.text('SELECT "key", code, name FROM offerings')).all()
    keys = [key for key, code, name in offerings if IS_61A.search(code or name or "")]
    for key in keys:
        # Offerings without a course_config row get one (with no link) on their
        # next page load, as before; their admins can add the link then.
        bind.execute(sa.text("UPDATE course_config SET staff_url = :url WHERE course = :key"),
                     {"url": CS61A_STAFF_URL, "key": key})


def downgrade():
    with op.batch_alter_table("course_config") as batch:
        batch.drop_column("staff_url")
