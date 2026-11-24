"""trip_tracking: the employee's per-trip choice about live tracking

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-23
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _tables():
    return set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())


def _as_datetime(value):
    """SQLite hands back text, PostgreSQL a datetime."""
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def upgrade() -> None:
    if "trip_tracking" in _tables():
        return
    table = op.create_table(
        "trip_tracking",
        sa.Column("expense_id", sa.Integer(),
                  sa.ForeignKey("expenses.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
    )
    if op.get_context().as_sql or "location_pings" not in _tables():
        return
    # Trips that were already being tracked before this change were tracked with the employee's agreement
    # (they accepted the old dialog), so keep them visible: mark them as allowed.
    rows = op.get_bind().execute(sa.text(
        "SELECT expense_id, MIN(received_at) FROM location_pings GROUP BY expense_id"
    )).fetchall()
    if rows:
        op.bulk_insert(table, [{"expense_id": r[0], "allowed": True, "decided_at": _as_datetime(r[1])} for r in rows])


def downgrade() -> None:
    op.drop_table("trip_tracking")
