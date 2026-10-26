"""Make databases moved from the monorepo match the models.

Revision ID: 0003_schema_cleanup
Revises: 0002_single_user
Create Date: 2026-10-26

The monorepo's MySQL-to-Postgres conversion left index and constraint names
like idx_18536_primary and attendance_ibfk_1, foreign keys with ON DELETE
RESTRICT, missing indexes and a missing foreign key (session.section_id), and
an unused flask_sessions table. This brings such a database in line with one
built from these migrations; on one that already matches, it changes nothing.
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_schema_cleanup"
down_revision = "0002_single_user"
branch_labels = None
depends_on = None

# (table, index name, columns) that the models declare.
INDEXES = [
    ("attendance", "ix_attendance_course", ["course"]),
    ("attendance", "ix_attendance_session_id", ["session_id"]),
    ("attendance", "ix_attendance_student_id", ["student_id"]),
    ("course_config", "ix_course_config_course", ["course"]),
    ("section", "ix_section_course", ["course"]),
    ("section", "ix_section_staff_id", ["staff_id"]),
    ("session", "ix_session_course", ["course"]),
    ("session", "ix_session_section_id", ["section_id"]),
    ("user_section", "ix_user_section_section_id", ["section_id"]),
]
# (table, column, referred table) foreign keys, named as Postgres names them by default.
FOREIGN_KEYS = [
    ("attendance", "session_id", "session"),
    ("session", "section_id", "section"),
    ("user_section", "section_id", "section"),
]


def _ensure_index(bind, table, name, columns):
    existing = sa.inspect(bind).get_indexes(table)
    if any(index["name"] == name for index in existing):
        return
    same_columns = [index for index in existing
                    if index["column_names"] == columns and not index.get("unique")]
    if same_columns and bind.dialect.name == "postgresql":
        op.execute(f'ALTER INDEX "{same_columns[0]["name"]}" RENAME TO "{name}"')
    else:
        op.create_index(name, table, columns)


def _ensure_foreign_key(bind, table, column, referred):
    name = f"{table}_{column}_fkey"
    matching = [fk for fk in sa.inspect(bind).get_foreign_keys(table)
                if fk["constrained_columns"] == [column]]
    if [fk["name"] for fk in matching] == [name] and not matching[0]["options"]:
        return
    for fk in matching:
        op.drop_constraint(fk["name"], table, type_="foreignkey")
    op.create_foreign_key(name, table, referred, [column], ["id"])


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("flask_sessions"):
        op.drop_table("flask_sessions")

    with op.batch_alter_table("section") as batch:
        batch.alter_column("location", existing_type=sa.String(length=255), nullable=True)

    for table, name, columns in INDEXES:
        _ensure_index(bind, table, name, columns)

    # SQLite databases are only ever built by these migrations, so their keys
    # already match; the rest is about names and options Postgres keeps.
    if bind.dialect.name != "postgresql":
        return

    for table, column, referred in FOREIGN_KEYS:
        _ensure_foreign_key(bind, table, column, referred)

    for table in sa.inspect(bind).get_table_names():
        primary_key = sa.inspect(bind).get_pk_constraint(table)
        if primary_key["name"] and primary_key["name"] != f"{table}_pkey":
            op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{primary_key["name"]}" TO "{table}_pkey"')

    # Converted indexes the models don't declare (and nothing queries by).
    for table in sa.inspect(bind).get_table_names():
        for index in sa.inspect(bind).get_indexes(table):
            if index["name"].startswith("idx_"):
                op.drop_index(index["name"], table_name=table)


def downgrade():
    # Restoring the converted names and RESTRICT options isn't useful.
    raise NotImplementedError("The schema cleanup can't be downgraded.")
