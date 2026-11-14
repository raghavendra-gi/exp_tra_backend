"""bill_hashes: a SHA-256 fingerprint of every attached bill, to catch duplicate bills

One row per bill in an expense's `receipt` / `ticketBill` field. Existing requests are
filled in batches. The helpers below are frozen copies of bills.py, so this migration
keeps working if that file changes.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14
"""
import base64
import hashlib
import json

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

BATCH = 50
BILL_FIELDS = ("receipt", "ticketBill")


def _fingerprints(data):
    out = []
    if not isinstance(data, dict):
        return out
    for field in BILL_FIELDS:
        for item in data.get(field) or []:
            url = item.get("dataUrl") if isinstance(item, dict) else None
            if not isinstance(url, str) or "," not in url:
                continue
            try:
                raw = base64.b64decode(url.split(",", 1)[1], validate=False)
            except (ValueError, TypeError):
                continue
            if raw:
                out.append((field, str(item.get("name") or "bill")[:255], hashlib.sha256(raw).hexdigest()))
    return out


def upgrade() -> None:
    op.create_table(
        "bill_hashes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("expense_id", sa.Integer(), sa.ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.String(length=50), nullable=False),
        sa.Column("field_key", sa.String(length=50), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_bill_hashes_sha256", "bill_hashes", ["sha256"])
    op.create_index("ix_bill_hashes_expense_id", "bill_hashes", ["expense_id"])
    if op.get_context().as_sql:
        return   # `--sql`: no rows to read

    bind = op.get_bind()
    expenses = sa.table("expenses", sa.column("id", sa.Integer), sa.column("employee_id", sa.String), sa.column("data", sa.JSON))
    hashes = sa.table(
        "bill_hashes", sa.column("sha256", sa.String), sa.column("expense_id", sa.Integer),
        sa.column("employee_id", sa.String), sa.column("field_key", sa.String), sa.column("filename", sa.String),
    )
    last_id = 0
    while True:
        rows = bind.execute(
            sa.select(expenses.c.id, expenses.c.employee_id, expenses.c.data)
            .where(expenses.c.id > last_id).order_by(expenses.c.id).limit(BATCH)
        ).all()
        if not rows:
            break
        for expense_id, employee_id, data in rows:
            if isinstance(data, str):
                data = json.loads(data)
            for field, name, sha in _fingerprints(data):
                bind.execute(hashes.insert().values(
                    sha256=sha, expense_id=expense_id, employee_id=employee_id, field_key=field, filename=name))
        last_id = rows[-1][0]


def downgrade() -> None:
    op.drop_index("ix_bill_hashes_expense_id", table_name="bill_hashes")
    op.drop_index("ix_bill_hashes_sha256", table_name="bill_hashes")
    op.drop_table("bill_hashes")
