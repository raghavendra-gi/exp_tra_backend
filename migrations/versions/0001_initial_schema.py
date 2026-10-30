"""Initial schema: users, expenses, expense_history, files

This is the schema the app used to create with Base.metadata.create_all().
Every step checks what already exists, so it is safe on:
  * a brand-new, empty database  -> creates everything
  * the existing production database (tables already made by create_all)
    -> creates nothing, and from now on the database is version-tracked.

Revision ID: 0001
Revises:
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _offline():
    # `alembic upgrade head --sql` has no live database to inspect: emit everything.
    return op.get_context().as_sql


def _tables():
    return set() if _offline() else set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table):
    return set() if _offline() else {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes(table)}


def _index(name, table, cols, unique=False):
    if name not in _indexes(table):
        op.create_index(name, table, cols, unique=unique)


def upgrade() -> None:
    existing = _tables()

    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("username", sa.String(50), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("display_name", sa.String(100), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    _index("ix_users_id", "users", ["id"])
    _index("ix_users_username", "users", ["username"], unique=True)

    if "expenses" not in existing:
        op.create_table(
            "expenses",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("employee_id", sa.String(50), sa.ForeignKey("users.username"), nullable=False),
            sa.Column("employee_name", sa.String(100), nullable=False),
            sa.Column("type", sa.String(50), nullable=False),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("created_date", sa.DateTime(), nullable=True),
            sa.Column("submitted_date", sa.DateTime(), nullable=True),
            sa.Column("decided_by", sa.String(100), nullable=True),
            sa.Column("decided_by_role", sa.String(20), nullable=True),
            sa.Column("decided_date", sa.DateTime(), nullable=True),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
        )
    _index("ix_expenses_employee_id", "expenses", ["employee_id"])
    _index("ix_expenses_type", "expenses", ["type"])
    _index("ix_expenses_status", "expenses", ["status"])

    if "expense_history" not in existing:
        op.create_table(
            "expense_history",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("expense_id", sa.Integer(),
                      sa.ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False),
            sa.Column("at", sa.DateTime(), nullable=True),
            sa.Column("by", sa.String(100), nullable=True),
            sa.Column("action", sa.String(255), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
        )
    _index("ix_expense_history_expense_id", "expense_history", ["expense_id"])

    if "files" not in existing:
        op.create_table(
            "files",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("expense_id", sa.Integer(),
                      sa.ForeignKey("expenses.id", ondelete="CASCADE"), nullable=True),
            sa.Column("field_key", sa.String(50), nullable=True),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(100), nullable=False),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column("storage_path", sa.String(500), nullable=False),
            sa.Column("uploaded_by", sa.String(50), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        )
    _index("ix_files_expense_id", "files", ["expense_id"])


def downgrade() -> None:
    op.drop_table("files")
    op.drop_table("expense_history")
    op.drop_table("expenses")
    op.drop_table("users")
