"""
Duplicate-bill detection.

Every bill a person attaches (the `receipt` and `ticketBill` fields) is fingerprinted
with SHA-256 over its bytes. The fingerprints live in the `bill_hashes` table, one row
per attached bill, so a new bill can be checked with one indexed lookup - the
base64 photos inside `expenses.data` are never read.

A bill is a duplicate when the same fingerprint is already on:
  * another request that is not Rejected (a rejected request may be fixed and
    resubmitted with the same bill, so it does not block anything), or
  * the same submission twice.
A request never clashes with itself, so editing or resubmitting keeps working.

Only identical files are caught. Two different photos of one paper bill have different
bytes, so they are not detected.
"""
import base64
import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models

# Fields of an expense that hold bills. Meter photos are deliberately not listed.
BILL_FIELDS = ("receipt", "ticketBill")

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class Bill:
    field: str
    name: str
    sha256: str


def is_sha256(value) -> bool:
    return isinstance(value, str) and bool(_HEX64.match(value))


def _decode_data_url(url) -> Optional[bytes]:
    """Bytes of a `data:<type>;base64,<payload>` URL, or None if it is not one."""
    if not isinstance(url, str) or "," not in url:
        return None
    try:
        return base64.b64decode(url.split(",", 1)[1], validate=False)
    except (ValueError, TypeError):
        return None


def collect(data) -> list[Bill]:
    """Fingerprint every bill in an expense's `data` (the server computes it - never the client)."""
    bills: list[Bill] = []
    if not isinstance(data, dict):
        return bills
    for field in BILL_FIELDS:
        items = data.get(field)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            raw = _decode_data_url(item.get("dataUrl"))
            if not raw:
                continue
            bills.append(Bill(field, str(item.get("name") or "bill")[:255], hashlib.sha256(raw).hexdigest()))
    return bills


def _existing(db: Session, hashes: Iterable[str], exclude_expense_id: Optional[int]) -> dict:
    """{sha256: (expense_id, type, status, employee_id)} for the first live request holding each hash."""
    hashes = list(set(hashes))
    if not hashes:
        return {}
    q = (
        db.query(models.BillHash.sha256, models.Expense.id, models.Expense.type,
                 models.Expense.status, models.Expense.employee_id)
        .join(models.Expense, models.Expense.id == models.BillHash.expense_id)
        .filter(models.BillHash.sha256.in_(hashes), models.Expense.status != "Rejected")
        .order_by(models.Expense.id)
    )
    if exclude_expense_id is not None:
        q = q.filter(models.BillHash.expense_id != exclude_expense_id)
    found: dict = {}
    for sha, eid, etype, status, owner in q.all():
        found.setdefault(sha, (eid, etype, status, owner))
    return found


def _message(name: str, hit: tuple, username: str) -> str:
    eid, etype, status, owner = hit
    where = f"your request #{eid} ({etype}, {status})" if owner == username else "another employee's request"
    return f'Duplicate bill: "{name}" was already submitted in {where}. Remove it and attach a different bill.'


def duplicate_messages(
    db: Session, bills: list[Bill], username: str, exclude_expense_id: Optional[int] = None
) -> dict:
    """{sha256: message} for each bill that is already on file or repeated within `bills`."""
    out: dict = {}
    seen: set = set()
    for b in bills:                                   # the same file attached twice in one form
        if b.sha256 in seen:
            out[b.sha256] = f'Duplicate bill: "{b.name}" is attached more than once. Keep only one copy.'
        seen.add(b.sha256)
    hits = _existing(db, [b.sha256 for b in bills], exclude_expense_id)
    for b in bills:
        if b.sha256 in hits and b.sha256 not in out:
            out[b.sha256] = _message(b.name, hits[b.sha256], username)
    return out


def reject_duplicates(
    db: Session, data, username: str, exclude_expense_id: Optional[int] = None
) -> list[Bill]:
    """Raise 409 when any bill in `data` is a duplicate. Returns the fingerprints for save()."""
    bills = collect(data)
    dupes = duplicate_messages(db, bills, username, exclude_expense_id)
    if dupes:
        raise HTTPException(status_code=409, detail=" ".join(dict.fromkeys(dupes.values())))
    return bills


def save(db: Session, expense_id: int, employee_id: str, bills: list[Bill]) -> None:
    """Replace the stored fingerprints of one request (create, edit and resubmit all end here)."""
    db.query(models.BillHash).filter(models.BillHash.expense_id == expense_id).delete(synchronize_session=False)
    for b in bills:
        db.add(models.BillHash(
            sha256=b.sha256, expense_id=expense_id, employee_id=employee_id,
            field_key=b.field, filename=b.name,
        ))
    db.commit()
