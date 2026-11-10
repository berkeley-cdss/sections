"""Make offerings.canvas_id a 64-bit integer.

Revision ID: 0008_bigint_offering_canvas_id
Revises: 0007_canvas_tokens
Create Date: 2026-11-10

Canvas gives a course on another shard a global ID (shard * 10**13 + local ID,
e.g. 30000002702310), which doesn't fit in a 32-bit integer. Postgres refused
the /offerings query for anyone enrolled in such a course, so the page failed
to load for them.
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_bigint_offering_canvas_id"
down_revision = "0007_canvas_tokens"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("offerings") as batch:
        batch.alter_column("canvas_id", existing_type=sa.Integer(), type_=sa.BigInteger(),
                           existing_nullable=False)


def downgrade():
    # Fails if an offering has an ID too big for a 32-bit integer.
    with op.batch_alter_table("offerings") as batch:
        batch.alter_column("canvas_id", existing_type=sa.BigInteger(), type_=sa.Integer(),
                           existing_nullable=False)
