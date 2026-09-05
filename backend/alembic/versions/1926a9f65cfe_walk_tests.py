"""six-minute walk tests, and the anthropometrics its equations need

Revision ID: 1926a9f65cfe
Revises: 15bf02cfcb80
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "1926a9f65cfe"
down_revision: Union[str, None] = "15bf02cfcb80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Height and sex are added solely for the 6MWT predicted-distance equation;
    # both are nullable because a test can be recorded without a prediction.
    with op.batch_alter_table("patient_profiles") as batch:
        batch.add_column(sa.Column("height_cm", sa.Float(), nullable=True))
        batch.add_column(sa.Column("sex_at_birth", sa.String(length=20), nullable=True))

    op.create_table(
        "walk_tests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("conducted_by_id", sa.String(length=36), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("course_length_m", sa.Float(), nullable=False),
        sa.Column("laps", sa.Integer(), nullable=True),
        sa.Column("partial_lap_m", sa.Float(), nullable=True),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("pre_heart_rate", sa.Integer(), nullable=True),
        sa.Column("pre_spo2", sa.Integer(), nullable=True),
        sa.Column("pre_systolic", sa.Integer(), nullable=True),
        sa.Column("pre_diastolic", sa.Integer(), nullable=True),
        sa.Column("pre_borg_dyspnoea", sa.Float(), nullable=True),
        sa.Column("pre_borg_fatigue", sa.Float(), nullable=True),
        sa.Column("lowest_spo2", sa.Integer(), nullable=True),
        sa.Column("rest_count", sa.Integer(), nullable=False),
        sa.Column("rest_seconds", sa.Integer(), nullable=False),
        sa.Column("post_heart_rate", sa.Integer(), nullable=True),
        sa.Column("post_spo2", sa.Integer(), nullable=True),
        sa.Column("post_systolic", sa.Integer(), nullable=True),
        sa.Column("post_diastolic", sa.Integer(), nullable=True),
        sa.Column("post_borg_dyspnoea", sa.Float(), nullable=True),
        sa.Column("post_borg_fatigue", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("stop_reason", sa.String(length=200), nullable=True),
        sa.Column("symptoms", sa.Text(), nullable=True),
        sa.Column("used_oxygen", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("predicted_distance_m", sa.Float(), nullable=True),
        sa.Column("percent_predicted", sa.Float(), nullable=True),
        sa.Column("below_lower_limit", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patient_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conducted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_walk_tests_patient_performed", "walk_tests", ["patient_id", "performed_at"])
    op.create_index(op.f("ix_walk_tests_created_at"), "walk_tests", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_walk_tests_created_at"), table_name="walk_tests")
    op.drop_index("ix_walk_tests_patient_performed", table_name="walk_tests")
    op.drop_table("walk_tests")
    with op.batch_alter_table("patient_profiles") as batch:
        batch.drop_column("sex_at_birth")
        batch.drop_column("height_cm")
