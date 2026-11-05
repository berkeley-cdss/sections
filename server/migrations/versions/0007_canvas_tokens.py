"""Add canvas_tokens, staff's Canvas access tokens kept on the server instead
of in the session cookie.

Revision ID: 0007_canvas_tokens
Revises: 0006_api_keys
Create Date: 2026-11-04

Tokens already in session cookies aren't moved: they're dropped from each
cookie on its next request (see login.py), and expire within an hour anyway.
Staff whose token is dropped sign in again before adding new students.
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_canvas_tokens"
down_revision = "0006_api_keys"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "canvas_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("handle_hash", sa.String(length=64), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_canvas_tokens_user_id", "canvas_tokens", ["user_id"])
    op.create_index("ix_canvas_tokens_handle_hash", "canvas_tokens", ["handle_hash"], unique=True)


def downgrade():
    op.drop_table("canvas_tokens")
