"""Baseline: the schema as of PR #14, before migrations existed.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-09 12:09:13.121880

Databases created before this (staging, whose data came from the monorepo)
already have these tables, so upgrading them only records this revision.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table("offerings"):
        return
    op.create_table('account',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('canvas_id', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('is_global_admin', sa.Boolean(), nullable=False),
    sa.Column('canvas_courses', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('account', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_account_canvas_id'), ['canvas_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_account_email'), ['email'], unique=False)

    op.create_table('course_config',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course', sa.String(length=255), nullable=True),
    sa.Column('can_students_join_lab', sa.Boolean(), nullable=True),
    sa.Column('can_students_change_lab', sa.Boolean(), nullable=True),
    sa.Column('can_tutors_change_lab', sa.Boolean(), nullable=True),
    sa.Column('can_tutors_reassign_lab', sa.Boolean(), nullable=True),
    sa.Column('can_students_join_disc', sa.Boolean(), nullable=True),
    sa.Column('can_students_change_disc', sa.Boolean(), nullable=True),
    sa.Column('can_tutors_change_disc', sa.Boolean(), nullable=True),
    sa.Column('can_tutors_reassign_disc', sa.Boolean(), nullable=True),
    sa.Column('can_students_join_tutoring', sa.Boolean(), nullable=True),
    sa.Column('can_students_change_tutoring', sa.Boolean(), nullable=True),
    sa.Column('can_tutors_change_tutoring', sa.Boolean(), nullable=True),
    sa.Column('can_tutors_reassign_tutoring', sa.Boolean(), nullable=True),
    sa.Column('message', sa.String(length=1024), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('course_config', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_course_config_course'), ['course'], unique=False)

    op.create_table('offerings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('canvas_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('code', sa.String(length=255), nullable=True),
    sa.Column('start_at', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    with op.batch_alter_table('offerings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_offerings_canvas_id'), ['canvas_id'], unique=True)

    op.create_table('user',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course', sa.String(length=255), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('is_staff', sa.Boolean(), nullable=True),
    sa.Column('is_admin', sa.Boolean(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_course'), ['course'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_email'), ['email'], unique=False)

    op.create_table('section',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course', sa.String(length=255), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('capacity', sa.Integer(), nullable=True),
    sa.Column('can_self_enroll', sa.Boolean(), nullable=True),
    sa.Column('enrollment_code', sa.String(length=255), nullable=True),
    sa.Column('staff_id', sa.Integer(), nullable=True),
    sa.Column('tag_string', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('start_time', sa.Integer(), nullable=True),
    sa.Column('end_time', sa.Integer(), nullable=True),
    sa.Column('location', sa.String(length=255), nullable=False),
    sa.Column('call_link', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['staff_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('section', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_section_course'), ['course'], unique=False)

    op.create_table('session',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course', sa.String(length=255), nullable=True),
    sa.Column('start_time', sa.Integer(), nullable=True),
    sa.Column('section_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['section_id'], ['section.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('session', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_session_course'), ['course'], unique=False)
        batch_op.create_index(batch_op.f('ix_session_section_id'), ['section_id'], unique=False)

    op.create_table('user_section',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('section_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['section_id'], ['section.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'section_id')
    )
    op.create_table('attendance',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course', sa.String(length=255), nullable=True),
    sa.Column('status', sa.Enum('present', 'excused', 'absent', name='attendance_status'), nullable=True),
    sa.Column('session_id', sa.Integer(), nullable=True),
    sa.Column('student_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['session.id'], ),
    sa.ForeignKeyConstraint(['student_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('attendance', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_attendance_course'), ['course'], unique=False)
        batch_op.create_index(batch_op.f('ix_attendance_session_id'), ['session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_attendance_student_id'), ['student_id'], unique=False)


def downgrade():
    # Dropping the baseline would drop every table, including pre-existing data.
    raise NotImplementedError("The baseline migration can't be downgraded.")
