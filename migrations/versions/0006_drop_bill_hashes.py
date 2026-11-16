"""Drop bill_hashes: duplicate bills are now only detected inside one expense

0005 added a table of bill fingerprints so a bill could be compared with other expenses.
That comparison was removed; the check now only looks at the files of the expense being
saved, so the table is not needed. Safe on databases that never had it.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().as_sql or "bill_hashes" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("bill_hashes")


def downgrade() -> None:
    pass   # nothing to restore: the table was only a cache of fingerprints
