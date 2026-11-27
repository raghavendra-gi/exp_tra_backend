"""
Duplicate-bill detection - inside ONE expense only (bills, and start vs end meter photos).

The files attached to a bill field (`receipt`, `ticketBill`) are fingerprinted with SHA-256
over their bytes. If the same file is attached twice to the same expense (for example one
bill uploaded for both Lunch and Dinner) the request is rejected with 409.

Nothing is compared across expenses: the same bill on another request, by you or by anyone
else, is accepted. Nothing is read from or written to the database for this check.

Only identical files are caught. Two different photos of one paper bill have different
bytes, so they are not detected.

Compatibility: an earlier version of routers/expenses.py called these functions with a
database session and also saved fingerprints (reject_duplicates(db, data, user), save(...),
duplicate_messages(...)). Those calls still work and do nothing beyond the one-expense
check, so this single file is enough to switch the rule, whichever expenses.py you have.
"""
import base64
import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException

logging.getLogger("uvicorn.error").info("[bills] duplicate bills are checked inside one expense only")

# Fields of an expense that hold bills.
BILL_FIELDS = ("receipt", "ticketBill")

# Meter photos. Start and end meter of ONE expense must not be the same picture, so these are
# fingerprinted too and compared with each other (never with the bill fields above).
# Car/Bike trip: startMeter / endMeter.  Regional Trip: startMeterImage / endMeterImage.
METER_FIELDS = {
    "startMeter": "Start meter",
    "endMeter": "End meter",
    "startMeterImage": "Start meter image",
    "endMeterImage": "End meter image",
}

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
    """Fingerprint of every bill file in an expense's `data`."""
    bills: list[Bill] = []
    if not isinstance(data, dict):
        return bills
    for field in BILL_FIELDS:
        items = data.get(field)
        if not isinstance(items, list):
            continue
        for item in items:
            raw = _decode_data_url(item.get("dataUrl")) if isinstance(item, dict) else None
            if raw:
                bills.append(Bill(field, str(item.get("name") or "bill")[:255], hashlib.sha256(raw).hexdigest()))
    return bills


def collect_meters(data) -> list[Bill]:
    """Fingerprint of every meter photo in an expense's `data`."""
    out: list[Bill] = []
    if not isinstance(data, dict):
        return out
    for field in METER_FIELDS:
        items = data.get(field)
        if not isinstance(items, list):
            continue
        for item in items:
            raw = _decode_data_url(item.get("dataUrl")) if isinstance(item, dict) else None
            if raw:
                out.append(Bill(field, str(item.get("name") or "meter")[:255], hashlib.sha256(raw).hexdigest()))
    return out


def _reject_duplicate_meters(data) -> None:
    first_seen: dict = {}      # sha256 -> field where it was first used
    clashes: list = []         # (file name, first field, second field)
    for m in collect_meters(data):
        if m.sha256 in first_seen:
            clashes.append((m.name, first_seen[m.sha256], m.field))
        else:
            first_seen[m.sha256] = m.field
    if clashes:
        parts = []
        for name, a, b in dict.fromkeys(clashes):
            parts.append(
                f'"{name}" is attached twice in {METER_FIELDS[a]}' if a == b
                else f'"{name}" is used for both {METER_FIELDS[a]} and {METER_FIELDS[b]}'
            )
        # starts with "Duplicate bill" so the frontend shows it on the field (see ExpenseFormPage)
        raise HTTPException(status_code=409, detail="Duplicate bill: " + "; ".join(parts) + ". Upload a different photo.")


def reject_duplicates(*args, **_ignored) -> list[Bill]:
    """
    Raise 409 when the same file is attached more than once to this expense.
    Call it as reject_duplicates(data); the older reject_duplicates(db, data, username, ...) also works.
    """
    data = next((a for a in args if isinstance(a, dict)), None)
    _reject_duplicate_meters(data)
    bills = collect(data)
    seen: set = set()
    repeated: list = []
    for b in bills:
        if b.sha256 in seen:
            repeated.append(b.name)
        seen.add(b.sha256)
    if repeated:
        names = ", ".join(f'"{n}"' for n in dict.fromkeys(repeated))
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate bill: {names} is attached more than once. Keep only one copy.",
        )
    return bills


def duplicate_messages(*_args, **_kwargs) -> dict:
    """Compatibility: other expenses are never searched, so there is never anything to report."""
    return {}


def save(*_args, **_kwargs) -> None:
    """Compatibility: nothing is stored any more."""