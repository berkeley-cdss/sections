"""Add api_keys, per-person keys for one offering's API, and
users.canvas_synced_at, which they check roles' age against (#29).

Revision ID: 0006_api_keys
Revises: 0005_staff_url
Create Date: 2026-11-04

Replaces the deployment-wide API_SECRET. Existing users get no
canvas_synced_at, so their keys (once made) need a fresh sign-in first.
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_api_keys"
down_revision = "0005_staff_url"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("canvas_synced_at", sa.Integer(), nullable=True))

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course", sa.String(length=255), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("hint", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.Integer(), nullable=True),
    )
    op.create_index("ix_api_keys_course", "api_keys", ["course"])
    op.create_index("ix_api_keys_owner_id", "api_keys", ["owner_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)


def downgrade():
    op.drop_table("api_keys")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("canvas_synced_at")
