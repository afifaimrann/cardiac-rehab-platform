"""appointments, direct messages, the clinician assistant thread, and avatars

Also stores the six-minute walk test's screening answers on the test itself, so
a later test can offer them back for confirmation rather than asking again.

Revision ID: 4c3d8b1a90ef
Revises: 1926a9f65cfe
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4c3d8b1a90ef"
down_revision: Union[str, None] = "1926a9f65cfe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- screening answers kept with the test ------------------------------
    with op.batch_alter_table("walk_tests") as batch:
        batch.add_column(sa.Column("screen_acs_within_30_days", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("screen_unstable_angina", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("screen_syncope_history", sa.Boolean(), nullable=True))
        batch.add_column(
            sa.Column("screen_acute_respiratory_failure", sa.Boolean(), nullable=True)
        )

    # --- profile photograph -------------------------------------------------
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("avatar_filename", sa.String(length=120), nullable=True))

    # --- clinician rota -----------------------------------------------------
    op.create_table(
        "availability_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("clinician_id", sa.String(length=36), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("slot_minutes", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["clinician_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_availability_clinician_weekday", "availability_rules",
        ["clinician_id", "weekday"],
    )
    op.create_index(
        op.f("ix_availability_rules_created_at"), "availability_rules", ["created_at"]
    )

    # --- appointments -------------------------------------------------------
    op.create_table(
        "appointments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("clinician_id", sa.String(length=36), nullable=False),
        # Nullable and unique together: cleared on cancellation so the time
        # becomes bookable again. NULLs do not collide under a unique index on
        # either SQLite or Postgres, which is what makes this work without a
        # partial index.
        sa.Column("slot_key", sa.String(length=80), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.Column("meeting_provider", sa.String(length=20), nullable=True),
        sa.Column("meeting_url", sa.String(length=500), nullable=True),
        sa.Column("meeting_room", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cancelled_by_id", sa.String(length=36), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=300), nullable=True),
        sa.Column("clinician_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patient_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinician_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cancelled_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slot_key", name="uq_appointments_slot"),
    )
    op.create_index("ix_appointments_patient_start", "appointments", ["patient_id", "starts_at"])
    op.create_index(
        "ix_appointments_clinician_start", "appointments", ["clinician_id", "starts_at"]
    )
    op.create_index(op.f("ix_appointments_created_at"), "appointments", ["created_at"])

    # --- messaging ----------------------------------------------------------
    op.create_table(
        "direct_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("sender_id", sa.String(length=36), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patient_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_direct_messages_patient_sent", "direct_messages", ["patient_id", "sent_at"]
    )
    op.create_index(op.f("ix_direct_messages_created_at"), "direct_messages", ["created_at"])

    # --- clinician assistant thread ----------------------------------------
    op.create_table(
        "clinician_assistant_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("clinician_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tools_used", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["clinician_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patient_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_assistant_clinician_patient", "clinician_assistant_messages",
        ["clinician_id", "patient_id", "created_at"],
    )
    op.create_index(
        op.f("ix_clinician_assistant_messages_created_at"),
        "clinician_assistant_messages", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_clinician_assistant_messages_created_at"),
        table_name="clinician_assistant_messages",
    )
    op.drop_index("ix_assistant_clinician_patient", table_name="clinician_assistant_messages")
    op.drop_table("clinician_assistant_messages")

    op.drop_index(op.f("ix_direct_messages_created_at"), table_name="direct_messages")
    op.drop_index("ix_direct_messages_patient_sent", table_name="direct_messages")
    op.drop_table("direct_messages")

    op.drop_index(op.f("ix_appointments_created_at"), table_name="appointments")
    op.drop_index("ix_appointments_clinician_start", table_name="appointments")
    op.drop_index("ix_appointments_patient_start", table_name="appointments")
    op.drop_table("appointments")

    op.drop_index(op.f("ix_availability_rules_created_at"), table_name="availability_rules")
    op.drop_index("ix_availability_clinician_weekday", table_name="availability_rules")
    op.drop_table("availability_rules")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("avatar_filename")

    with op.batch_alter_table("walk_tests") as batch:
        batch.drop_column("screen_acute_respiratory_failure")
        batch.drop_column("screen_syncope_history")
        batch.drop_column("screen_unstable_angina")
        batch.drop_column("screen_acs_within_30_days")
