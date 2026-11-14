"""users.role_title: the label of a custom role typed on the Create Employee page

The column was added to models.py without a migration, so a database built from
the migrations (a new install, a fresh Render database) had no users.role_title and
every sign-in failed. Databases where it was added by hand are left alone.

Revision ID: 0004
Revises: ef64f4aa8768
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "ef64f4aa8768"
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline = op.get_context().as_sql
    if offline or "role_title" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}:
        op.add_column("users", sa.Column("role_title", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "role_title")
