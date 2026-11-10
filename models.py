from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON, Index, event, inspect
)
from sqlalchemy.orm import relationship

from database import Base
from timeutil import utcnow
from payload import strip_file_payloads


class User(Base):
    """Mirrors the USERS array hardcoded in the frontend (clerk / accounts / employee)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)          # clerk | accounts | op_head | employee
    display_name = Column(String(100), nullable=False)
    
    # New Profile Fields
    email = Column(String(100), unique=True, nullable=True)
    branch = Column(String(100), nullable=True)
    designation = Column(String(100), nullable=True)
    avatar = Column(Text, nullable=True)
    
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
    data_lite = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="Pending", index=True)

    created_date = Column(DateTime, default=utcnow)
    submitted_date = Column(DateTime, nullable=True)

    # Decision tracking fields
    decided_by = Column(String(100), nullable=True)
    decided_by_role = Column(String(20), nullable=True)  
    decided_date = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)       

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
    """Metadata for an uploaded receipt/photo."""
    __tablename__ = "files"

    id = Column(String(64), primary_key=True)
    expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="CASCADE"), nullable=True, index=True)
    field_key = Column(String(50), nullable=True)
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


EXTRA_INDEXES = [
    Index("ix_expenses_created_date", Expense.created_date),
    Index("ix_expenses_employee_created", Expense.employee_id, Expense.created_date),
]