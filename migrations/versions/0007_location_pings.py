"""location_pings: GPS points for live trip tracking

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _tables():
    return set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "location_pings" in _tables():
        return                      # already there (e.g. created by hand): nothing to do
    op.create_table(
        "location_pings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("expense_id", sa.Integer(),
                  sa.ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.String(50), sa.ForeignKey("users.username"), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("speed", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_location_pings_employee_id", "location_pings", ["employee_id"])
    op.create_index("ix_location_pings_recorded_at", "location_pings", ["recorded_at"])
    op.create_index("ix_location_pings_expense_time", "location_pings", ["expense_id", "recorded_at"])


def downgrade() -> None:
    op.drop_table("location_pings")
