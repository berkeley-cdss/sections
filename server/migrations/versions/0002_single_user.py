"""One User per person across all offerings, like seating.

Revision ID: 0002_single_user
Revises: 0001_baseline
Create Date: 2026-10-09

Before: a `user` row per person per offering (with that offering's is_staff and
is_admin), plus an `account` row per person who has logged in.
After: one `users` row per person (matched by email), with their roles in each
offering as sets of offering keys. Enrollments, attendance and section staff
are re-pointed at the merged rows.

Also drops tables nothing reads: `account`, the old `user`, `course` (left over
from renaming offerings), and `slot`, `survey` and `user_section_junction` (from
the monorepo), along with `session.slot_id`, the monorepo's link to `slot`.
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_single_user"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

# Tables with a foreign key to the old `user` table, and the column holding it.
USER_REFERENCES = [("attendance", "student_id"), ("section", "staff_id"), ("user_section", "user_id")]
# Tables from the monorepo (and the pre-rename `course`) that nothing reads.
LEFTOVER_TABLES = ("course", "slot", "survey")
# Gives SQLite's unnamed foreign keys a name, so batch mode can drop them.
FK_NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def _people(bind):
    """One dict per person, merged by email, from the old user and account rows."""
    meta = sa.MetaData()
    old_user = sa.Table("user", meta, autoload_with=bind)
    people = {}
    for row in bind.execute(sa.select(old_user).order_by(old_user.c.id)):
        person = people.setdefault(row.email.lower(), {
            "email": row.email, "name": row.name or row.email, "canvas_id": None,
            "is_global_admin": False, "canvas_courses": {},
            "staff": set(), "admin": set(), "student": set(), "old_ids": [],
        })
        person["old_ids"].append(row.id)
        if row.name:
            person["name"] = row.name  # rows are in id order, so the newest name wins
        if row.is_staff:
            person["staff"].add(row.course)
        else:
            person["student"].add(row.course)
        if row.is_admin:
            person["admin"].add(row.course)

    if sa.inspect(bind).has_table("account"):
        account = sa.Table("account", meta, autoload_with=bind)
        for row in bind.execute(sa.select(account)):
            person = people.setdefault(row.email.lower(), {
                "email": row.email, "name": row.name, "staff": set(), "admin": set(),
                "student": set(), "old_ids": [],
            })
            # Logged-in people get their Canvas name and details.
            person.update(name=row.name, canvas_id=row.canvas_id,
                          is_global_admin=bool(row.is_global_admin),
                          canvas_courses=row.canvas_courses or {})
    return people


def _drop_foreign_keys_to(table, referred):
    fks = [fk for fk in sa.inspect(op.get_bind()).get_foreign_keys(table)
           if fk["referred_table"] == referred]
    if not fks:
        return
    with op.batch_alter_table(table, naming_convention=FK_NAMING) as batch:
        for fk in fks:
            name = fk["name"] or f"fk_{table}_{fk['constrained_columns'][0]}_{referred}"
            batch.drop_constraint(name, type_="foreignkey")


def upgrade():
    bind = op.get_bind()

    users = op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("canvas_id", sa.String(length=255), nullable=True),
        sa.Column("is_global_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("canvas_courses", sa.JSON(), nullable=False),
        sa.Column("staff_offerings", sa.Text(), nullable=False, server_default=""),
        sa.Column("admin_offerings", sa.Text(), nullable=False, server_default=""),
        sa.Column("student_offerings", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_canvas_id", "users", ["canvas_id"], unique=True)

    people = _people(bind)
    for person in people.values():
        person["id"] = bind.execute(
            sa.insert(users).returning(users.c.id),
            {
                "email": person["email"], "name": person["name"],
                "canvas_id": person.get("canvas_id"),
                "is_global_admin": person.get("is_global_admin", False),
                "canvas_courses": person.get("canvas_courses") or {},
                "staff_offerings": ",".join(sorted(person["staff"])),
                "admin_offerings": ",".join(sorted(person["admin"])),
                "student_offerings": ",".join(sorted(person["student"])),
            },
        ).scalar_one()

    # Map every old per-offering row to its person, then re-point references.
    id_map = op.create_table(
        "user_id_map",
        sa.Column("old_id", sa.Integer(), primary_key=True),
        sa.Column("new_id", sa.Integer(), nullable=False),
    )
    mappings = [{"old_id": old_id, "new_id": person["id"]}
                for person in people.values() for old_id in person["old_ids"]]
    if mappings:
        op.bulk_insert(id_map, mappings)

    if sa.inspect(bind).has_table("user_section_junction"):
        op.drop_table("user_section_junction")
    for table, column in USER_REFERENCES:
        _drop_foreign_keys_to(table, "user")
        # Two steps, through negative ids: new ids overlap old ones, and
        # user_section's primary key is checked row by row during an UPDATE.
        bind.execute(sa.text(
            f"UPDATE {table} SET {column} = "
            f"-(SELECT new_id FROM user_id_map WHERE old_id = {table}.{column}) "
            f"WHERE {column} IS NOT NULL"
        ))
        bind.execute(sa.text(f"UPDATE {table} SET {column} = -{column} WHERE {column} < 0"))
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(f"fk_{table}_{column}_users", "users", [column], ["id"])
    op.drop_table("user_id_map")

    # Databases from the monorepo still link sessions to the old slot table.
    inspector = sa.inspect(bind)
    for table in inspector.get_table_names():
        if any(fk["referred_table"] in LEFTOVER_TABLES for fk in inspector.get_foreign_keys(table)):
            for referred in LEFTOVER_TABLES:
                _drop_foreign_keys_to(table, referred)
    if "slot_id" in {c["name"] for c in sa.inspect(bind).get_columns("session")}:
        with op.batch_alter_table("session") as batch:
            batch.drop_column("slot_id")

    inspector = sa.inspect(bind)
    for table in ("account", "user") + LEFTOVER_TABLES:
        if inspector.has_table(table):
            op.drop_table(table)


def downgrade():
    # Per-offering rows can't be recovered once merged.
    raise NotImplementedError("Merging users into one row per person can't be undone.")
