"""decided_by_role column (if missing) + indexes for the expense list

* expenses.decided_by_role was added to the model after some databases had
  already been created; create_all() never adds columns to an existing table,
  so older databases may lack it. Added here only if it isn't there.
* The list endpoint always sorts by created_date, and an employee's list is
  "WHERE employee_id = ? ORDER BY created_date DESC" - these two indexes
  serve exactly those queries.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().as_sql:          # `--sql`: no live database to inspect
        columns, indexes = {"decided_by_role"}, set()   # 0001 already emits the column
    else:
        insp = sa.inspect(op.get_bind())
        columns = {c["name"] for c in insp.get_columns("expenses")}
        indexes = {ix["name"] for ix in insp.get_indexes("expenses")}

    if "decided_by_role" not in columns:
        op.add_column("expenses", sa.Column("decided_by_role", sa.String(20), nullable=True))
    if "ix_expenses_created_date" not in indexes:
        op.create_index("ix_expenses_created_date", "expenses", ["created_date"])
    if "ix_expenses_employee_created" not in indexes:
        op.create_index("ix_expenses_employee_created", "expenses", ["employee_id", "created_date"])


def downgrade() -> None:
    op.drop_index("ix_expenses_employee_created", table_name="expenses")
    op.drop_index("ix_expenses_created_date", table_name="expenses")
    # decided_by_role is kept: older databases may have had it before 0002.
