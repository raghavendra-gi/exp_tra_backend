"""expenses.data_lite: the request data without attachment bytes

Lists, stats and the CSV export used to read the whole `data` column — every
receipt photo, base64-encoded — and throw the images away in Python. This
column holds the same data minus the `dataUrl` of each attachment, so those
endpoints never transfer photos from the database.

Existing rows are filled in batches. The function below is a frozen copy of
payload.strip_file_payloads, so this migration keeps working if that changes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-30
"""
import json

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

BATCH = 200


def _strip(data):
    if not isinstance(data, dict):
        return data
    out = {}
    for k, v in data.items():
        if isinstance(v, list) and any(isinstance(i, dict) and "dataUrl" in i for i in v):
            out[k] = [{kk: vv for kk, vv in i.items() if kk != "dataUrl"} if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


def upgrade() -> None:
    offline = op.get_context().as_sql
    if offline or "data_lite" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("expenses")}:
        op.add_column("expenses", sa.Column("data_lite", sa.JSON(), nullable=True))
    if offline:
        return   # `--sql`: no rows to read. The API fills the gap for NULL rows.

    bind = op.get_bind()
    expenses = sa.table("expenses", sa.column("id", sa.Integer), sa.column("data", sa.JSON), sa.column("data_lite", sa.JSON))
    last_id = 0
    while True:
        rows = bind.execute(
            sa.select(expenses.c.id, expenses.c.data)
            .where(expenses.c.data_lite.is_(None), expenses.c.id > last_id)
            .order_by(expenses.c.id)
            .limit(BATCH)
        ).all()
        if not rows:
            break
        for row_id, data in rows:
            if isinstance(data, str):          # some drivers hand JSON back as text
                data = json.loads(data)
            bind.execute(
                expenses.update().where(expenses.c.id == row_id).values(data_lite=_strip(data or {}))
            )
        last_id = rows[-1][0]


def downgrade() -> None:
    op.drop_column("expenses", "data_lite")
