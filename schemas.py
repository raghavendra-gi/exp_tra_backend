# schemas.py
from datetime import datetime
from typing import Annotated, Optional, List, Literal
from pydantic import BaseModel, Field, PlainSerializer, field_validator

from timeutil import as_utc

# Every datetime sent to the browser goes out as UTC with a trailing 'Z'.
UTCDateTime = Annotated[datetime, PlainSerializer(as_utc, return_type=datetime)]


# ───────── Auth ─────────
class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    email: Optional[str] = None
    branch: Optional[str] = None
    designation: Optional[str] = None
    avatar: Optional[str] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    branch: Optional[str] = None
    designation: Optional[str] = None
    avatar: Optional[str] = None


# ───────── History ─────────
class HistoryEntryOut(BaseModel):
    at: UTCDateTime
    by: str
    action: str
    note: Optional[str] = ""

    class Config:
        from_attributes = True


# ───────── Files ─────────
class FileOut(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    field_key: Optional[str] = None

    class Config:
        from_attributes = True


# ───────── Expenses ─────────
class ExpenseCreate(BaseModel):
    type: str
    data: dict = Field(default_factory=dict)
    stage: Optional[str] = None      # "start" -> first leg of a Regional Trip


class ExpenseUpdate(BaseModel):
    data: dict


class DecisionRequest(BaseModel):
    status: str                       # Approved | Rejected
    reason: Optional[str] = None


class BulkDecisionRequest(BaseModel):
    ids: List[int]
    status: str
    reason: Optional[str] = None


class QueryRequest(BaseModel):
    reason: str


class ExpenseHistoryOut(BaseModel):
    id: int
    at: UTCDateTime
    by: str
    action: str
    note: Optional[str] = None

    class Config:
        from_attributes = True


class ExpenseOut(BaseModel):
    id: int
    employee_id: str
    employee_name: str
    type: str
    data: dict
    status: str
    created_date: UTCDateTime
    submitted_date: Optional[UTCDateTime]
    decided_by: Optional[str]
    decided_by_role: Optional[str]
    decided_date: Optional[UTCDateTime]
    rejection_reason: Optional[str]
    history: List[ExpenseHistoryOut] = []

    class Config:
        from_attributes = True


class StatsOut(BaseModel):
    total: int
    total_amount: float
    approved: int
    approved_amount: float
    pending: int
    pending_amount: float
    rejected: int
    rejected_amount: float
    in_progress: int
    in_progress_amount: float


# ───────── Admin: create user ─────────
class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str
    # Changed to `str` to allow custom roles (e.g. "manager", "auditor")
    role: str = "employee"
    email: Optional[str] = None
    branch: Optional[str] = None
    designation: Optional[str] = None

    # In schemas.py
class FundUpdateRequest(BaseModel):
    employee_id: str          # username of the employee this fund is for
    year: int
    month: int
    amount: float

class FundOut(BaseModel):
    employee_id: Optional[str] = None   # None = all employees combined
    year: int
    month: int
    total_fund: float
    spent_amount: float
    remaining_amount: float