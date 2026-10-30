from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON, Index, event, inspect
)
from sqlalchemy.orm import relationship

from database import Base
from timeutil import utcnow
from payload import strip_file_payloads


class User(Base):
    """Mirrors the USERS array hardcoded in the frontend (head / hr / employee)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)          # head | hr | employee
    display_name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=utcnow)


class Expense(Base):
    """
    One row per submitted request, whatever its type (Pooja, Food, Plan Trip, ...).
    `data` stores the type-specific fields as JSON, exactly like the frontend's
    `expense.data` object - this avoids a separate table per expense type.
    """
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String(50), ForeignKey("users.username"), nullable=False, index=True)
    employee_name = Column(String(100), nullable=False)
    type = Column(String(50), nullable=False, index=True)
    data = Column(JSON, nullable=False, default=dict)
    # Same as `data` without attachment bytes. Lists, stats and CSV read only
    # this column, so they never pull receipt photos out of the database.
    # Kept in sync automatically (see the before_insert / before_update hooks below); NULL only for rows
    # written before migration 0003, which the API handles too.
    data_lite = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="Pending", index=True)
    # Pending | Approved | Rejected | In Progress (two-stage trips before they're ended)

    created_date = Column(DateTime, default=utcnow)
    submitted_date = Column(DateTime, nullable=True)

    # Decision tracking fields
    decided_by = Column(String(100), nullable=True)
    decided_by_role = Column(String(20), nullable=True)  # head | hr - who made the decision
    decided_date = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)       # Used for both approval notes and rejection reasons

    history = relationship(
        "ExpenseHistory", back_populates="expense",
        cascade="all, delete-orphan", order_by="[ExpenseHistory.at, ExpenseHistory.id]"
    )
    files = relationship("FileAsset", back_populates="expense")


class ExpenseHistory(Base):
    """Audit trail: submitted / edited / approved / rejected / resubmitted, etc."""
    __tablename__ = "expense_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True)
    at = Column(DateTime, default=utcnow)
    by = Column(String(100))
    action = Column(String(255))
    note = Column(Text, nullable=True)

    expense = relationship("Expense", back_populates="history")


class FileAsset(Base):
    """
    Metadata for an uploaded receipt/photo. The actual bytes live on disk under
    STORAGE_DIR; this row is what the frontend's IndexedDB file record becomes.
    """
    __tablename__ = "files"

    id = Column(String(64), primary_key=True)          # e.g. "f_3a9c1b..."
    expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="CASCADE"), nullable=True, index=True)
    field_key = Column(String(50), nullable=True)       # which form field, e.g. "receipt"
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)
    storage_path = Column(String(500), nullable=False)
    uploaded_by = Column(String(50), nullable=True)
    uploaded_at = Column(DateTime, default=utcnow)

    expense = relationship("Expense", back_populates="files")


@event.listens_for(Expense, "before_insert")
def _data_lite_on_insert(mapper, connection, target):
    target.data_lite = strip_file_payloads(target.data)


@event.listens_for(Expense, "before_update")
def _data_lite_on_update(mapper, connection, target):
    if inspect(target).attrs.data.history.has_changes():
        target.data_lite = strip_file_payloads(target.data)


# ── Extra indexes ──
# The list endpoint always orders by created_date, and an employee's list is
# "WHERE employee_id = ? ORDER BY created_date DESC". Created by migration 0002;
# declared here too so `alembic revision --autogenerate` sees no difference.
EXTRA_INDEXES = [
    Index("ix_expenses_created_date", Expense.created_date),
    Index("ix_expenses_employee_created", Expense.employee_id, Expense.created_date),
]
