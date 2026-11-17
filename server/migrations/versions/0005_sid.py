"""Add users.sid, the student ID number from Canvas, for roster photos.

Revision ID: 0005_sid
Revises: 0004_pronouns
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_sid"
down_revision = "0004_pronouns"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("sid", sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("sid")
