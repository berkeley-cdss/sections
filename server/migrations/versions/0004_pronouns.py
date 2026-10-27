"""Add users.pronouns, from Canvas at login.

Revision ID: 0004_pronouns
Revises: 0003_schema_cleanup
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_pronouns"
down_revision = "0003_schema_cleanup"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("pronouns", sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("pronouns")
