# schemas.py
from datetime import datetime
from typing import Annotated, Optional, List, Literal
from pydantic import BaseModel, Field, PlainSerializer, field_validator

from roles import ALLOWED_ROLES, clean_role_title
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
    role_title: Optional[str] = None
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

# Remove the spaces so it aligns with the other classes
class BillCheckRequest(BaseModel):
    # This class is used by expenses.py to check for duplicate bills before submitting
    data: dict = Field(default_factory=dict)


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
    role: str = "employee"                 # one of roles.ALLOWED_ROLES
    role_title: Optional[str] = None       # a typed custom label, e.g. "Area Manager" (role stays "employee")
    email: Optional[str] = None
    branch: Optional[str] = None
    designation: Optional[str] = None

    @field_validator("role")
    @classmethod
    def _valid_role(cls, v: str) -> str:
        if v not in ALLOWED_ROLES:
            raise ValueError("Invalid role")
        return v

    @field_validator("role_title")
    @classmethod
    def _tidy_role_title(cls, v):
        return clean_role_title(v)


# ───────── Accounts: manage users ─────────
class UserAdminOut(BaseModel):
    """One row of the Users page. No avatar: that is a large image and the list does not need it."""
    id: int
    username: str
    display_name: str
    role: str
    role_title: Optional[str] = None
    email: Optional[str] = None
    branch: Optional[str] = None
    designation: Optional[str] = None
    created_at: Optional[UTCDateTime] = None

    class Config:
        from_attributes = True


class UserAdminUpdate(BaseModel):
    """
    Only the fields that are sent are changed. For email, branch, designation and role_title
    an empty string clears the value. The username can never be changed.
    """
    display_name: Optional[str] = None
    role: Optional[str] = None
    role_title: Optional[str] = None
    email: Optional[str] = None
    branch: Optional[str] = None
    designation: Optional[str] = None
    new_password: Optional[str] = None     # blank = keep the current password

    @field_validator("display_name")
    @classmethod
    def _name(cls, v):
        if v is None:
            return v
        v = " ".join(v.split())
        if not v:
            raise ValueError("Enter the full name")
        if len(v) > 100:
            raise ValueError("The name must be 100 characters or fewer")
        return v

    @field_validator("role")
    @classmethod
    def _valid_role(cls, v):
        if v is not None and v not in ALLOWED_ROLES:
            raise ValueError("Invalid role")
        return v

    @field_validator("role_title")
    @classmethod
    def _tidy_role_title(cls, v):
        return None if v is None else (clean_role_title(v) or "")

    @field_validator("email", "branch", "designation")
    @classmethod
    def _trim(cls, v):
        return None if v is None else v.strip()[:100]

    @field_validator("new_password")
    @classmethod
    def _password(cls, v):
        if not v:
            return None
        if len(v) < 6:
            raise ValueError("Use at least 6 characters for the password")
        if len(v.encode("utf-8")) > 72:
            raise ValueError("The password is too long (72 characters at most)")
        return v

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