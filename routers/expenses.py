import csv
import io
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import asc, desc, insert, select, update
from sqlalchemy.orm import Session, selectinload

from deps import get_db, get_current_user, require_approver
from schemas import (
    ExpenseCreate, ExpenseUpdate, ExpenseOut, DecisionRequest,
    BulkDecisionRequest, StatsOut,
)
import models
from payload import expense_dict, expense_from_orm, history_dict, json_response, strip_file_payloads
from timeutil import utcnow, to_ist

router = APIRouter()

TWO_STAGE_TYPES = {"Regional Trip"}
APPROVER_ROLES = ("head", "hr")

# Columns the list endpoint may be sorted by. Anything else falls back to created_date.
SORTABLE = {
    "id", "created_date", "submitted_date", "decided_date",
    "status", "type", "employee_name",
}

E = models.Expense
H = models.ExpenseHistory

# Every Expense column except the two JSON payloads; lists pick one of them.
_BASE_COLUMNS = (
    E.id, E.employee_id, E.employee_name, E.type, E.status,
    E.created_date, E.submitted_date, E.decided_by, E.decided_by_role,
    E.decided_date, E.rejection_reason,
)


def _visible(stmt, user: models.User):
    """Employees only ever see their own requests; head/hr see everything."""
    if user.role not in APPROVER_ROLES:
        stmt = stmt.where(E.employee_id == user.username)
    return stmt


def _amount(data) -> float:
    try:
        return float((data or {}).get("amount") or 0)
    except (TypeError, ValueError, AttributeError):
        return 0.0


def _history_by_expense(db: Session, ids) -> dict:
    """History for many expenses in ONE query (instead of one per 500 rows)."""
    if not ids:
        return {}
    rows = db.execute(
        select(H.expense_id, H.id, H.at, H.by, H.action, H.note)
        .where(H.expense_id.in_(ids))
        .order_by(H.expense_id, H.at, H.id)
    ).all()
    out = defaultdict(list)
    for r in rows:
        out[r.expense_id].append(history_dict(r))
    return out


def _attach_pending_files(db: Session, expense: models.Expense, data: dict):
    """Link file ids (uploaded earlier via /api/files/upload) to this expense."""
    ids = []
    for v in (data or {}).values():
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict) and item.get("id"):
                    ids.append(item["id"])
    if not ids:
        return
    db.query(models.FileAsset).filter(models.FileAsset.id.in_(ids)).update(
        {models.FileAsset.expense_id: expense.id}, synchronize_session=False
    )
    db.commit()


@router.get("", response_model=list[ExpenseOut])
def list_expenses(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    type_filter: Optional[str] = Query(None, alias="type"),
    employee: Optional[str] = None,
    sort_by: str = "created_date",
    sort_dir: str = "desc",
    lite: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    `lite=1` returns the same rows without attachment bytes — read from the
    data_lite column, so photos never leave the database. Without it the
    response is exactly as before (full `data`).

    Two queries in total (rows, then all their history), and an ETag: when the
    list hasn't changed the browser gets an empty 304 and reuses its copy.
    """
    payload_col = E.data_lite if lite else E.data
    stmt = select(*_BASE_COLUMNS, payload_col.label("payload"), E.data_lite.is_(None).label("lite_missing"))
    stmt = _visible(stmt, current_user)
    if status_filter:
        stmt = stmt.where(E.status == status_filter)
    if type_filter:
        stmt = stmt.where(E.type == type_filter)
    if employee and current_user.role in APPROVER_ROLES:
        stmt = stmt.where(E.employee_id == employee)
    sort_col = getattr(E, sort_by if sort_by in SORTABLE else "created_date")
    stmt = stmt.order_by(desc(sort_col) if sort_dir == "desc" else asc(sort_col), desc(E.id))

    rows = db.execute(stmt).all()
    history = _history_by_expense(db, [r.id for r in rows])

    # Rows saved before migration 0003 ran have no data_lite yet: strip them here.
    missing = [r.id for r in rows if lite and r.lite_missing]
    full = dict(db.execute(select(E.id, E.data).where(E.id.in_(missing))).all()) if missing else {}

    out = []
    for r in rows:
        data = strip_file_payloads(full[r.id]) if r.id in full else r.payload
        out.append(expense_dict(r, data, history.get(r.id, ())))
    return json_response(out, request)


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Only status + the small data_lite column are read — no attachments.
    rows = db.execute(_visible(select(E.status, E.data_lite, E.id), current_user)).all()
    missing = [r.id for r in rows if r.data_lite is None]
    full = dict(db.execute(select(E.id, E.data).where(E.id.in_(missing))).all()) if missing else {}

    buckets = {s: [0, 0.0] for s in ("Approved", "Pending", "Rejected", "In Progress")}
    total_amount = 0.0
    for r in rows:
        amt = _amount(full.get(r.id, r.data_lite))
        total_amount += amt
        b = buckets.get(r.status)
        if b is not None:
            b[0] += 1
            b[1] += amt

    return StatsOut(
        total=len(rows), total_amount=total_amount,
        approved=buckets["Approved"][0], approved_amount=buckets["Approved"][1],
        pending=buckets["Pending"][0], pending_amount=buckets["Pending"][1],
        rejected=buckets["Rejected"][0], rejected_amount=buckets["Rejected"][1],
        in_progress=buckets["In Progress"][0], in_progress_amount=buckets["In Progress"][1],
    )


@router.get("/export/csv")
def export_csv(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    stmt = _visible(
        select(E.id, E.employee_name, E.type, E.data_lite, E.submitted_date, E.created_date),
        current_user,
    )
    if status_filter:
        stmt = stmt.where(E.status == status_filter)
    rows = db.execute(stmt.order_by(desc(E.created_date), desc(E.id))).all()
    missing = [r.id for r in rows if r.data_lite is None]
    full = dict(db.execute(select(E.id, E.data).where(E.id.in_(missing))).all()) if missing else {}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Name", "Type", "Amount (INR)", "Date", "Time"])
    total = 0.0
    for r in rows:
        amount = _amount(full.get(r.id, r.data_lite))
        total += amount
        submitted = r.submitted_date or r.created_date
        if submitted:
            submitted = to_ist(submitted)   # stored in UTC, exported in IST
        writer.writerow([
            r.employee_name, r.type, amount,
            submitted.strftime("%d-%b-%Y") if submitted else "",
            submitted.strftime("%H:%M") if submitted else "",
        ])
    writer.writerow(["TOTAL", "", total, "", ""])

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=expenses.csv"},
    )


@router.get("/{expense_id}", response_model=ExpenseOut)
def get_expense(
    expense_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    row = db.execute(
        _visible(select(*_BASE_COLUMNS, E.data.label("payload")), current_user).where(E.id == expense_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Expense not found")
    history = _history_by_expense(db, [row.id])
    return json_response(expense_dict(row, row.payload, history.get(row.id, ())), request)


def _load_for_update(db: Session, expense_id: int) -> models.Expense:
    e = (
        db.query(E)
        .options(selectinload(E.history))
        .filter(E.id == expense_id)
        .first()
    )
    if not e:
        raise HTTPException(status_code=404, detail="Expense not found")
    return e


def _push_history(expense: models.Expense, by: str, action: str, note: str = "", at=None):
    expense.history.append(H(by=by, action=action, note=note, at=at or utcnow()))


@router.post("", response_model=ExpenseOut)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role != "employee":
        raise HTTPException(status_code=403, detail="Only employees submit expenses")

    now = utcnow()
    is_start = payload.type in TWO_STAGE_TYPES and payload.stage == "start"
    expense = E(
        employee_id=current_user.username,
        employee_name=current_user.display_name,
        type=payload.type,
        data=payload.data,
        status="In Progress" if is_start else "Pending",
        created_date=now,
        submitted_date=now,
    )
    _push_history(expense, current_user.display_name,
                  "Trip started" if is_start else "Submitted for approval", at=now)

    db.add(expense)
    db.commit()            # objects stay loaded after commit (expire_on_commit=False): no re-read
    _attach_pending_files(db, expense, payload.data)
    return json_response(expense_from_orm(expense))


@router.put("/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: int,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Handles three of the frontend's flows with one endpoint, based on current status:
      - In Progress -> closing leg of a two-stage trip (Regional Trip "end trip")
      - Pending      -> plain edit
      - Rejected     -> fix & resubmit
    """
    e = _load_for_update(db, expense_id)
    if e.employee_id != current_user.username:
        raise HTTPException(status_code=403, detail="You can only edit your own expenses")

    now = utcnow()
    if e.status == "In Progress":
        e.data = {**(e.data or {}), **payload.data}
        e.status = "Pending"
        e.submitted_date = now
        _push_history(e, current_user.display_name, "Trip ended and submitted for approval", at=now)
    elif e.status == "Pending":
        e.data = payload.data
        e.submitted_date = now
        _push_history(e, current_user.display_name, "Edited by employee", at=now)
    elif e.status == "Rejected":
        e.data = payload.data
        e.status = "Pending"
        e.submitted_date = now
        e.decided_by = None
        e.decided_date = None
        e.rejection_reason = None
        _push_history(e, current_user.display_name, "Resubmitted for approval", at=now)
    else:
        raise HTTPException(status_code=400, detail="Approved expenses cannot be edited")

    db.commit()
    _attach_pending_files(db, e, payload.data)
    return json_response(expense_from_orm(e))


def _decision_values(user: models.User, status: str, comment: str, now) -> dict:
    return {
        "status": status,
        "decided_by": user.display_name,
        "decided_by_role": user.role,
        "decided_date": now,
        # rejection_reason only holds a REJECTION reason. Approving clears any old one.
        "rejection_reason": comment if (status == "Rejected" and comment) else None,
    }


@router.post("/{expense_id}/decide", response_model=ExpenseOut)
def decide_expense(
    expense_id: int,
    payload: DecisionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_approver),
):
    if payload.status not in ("Approved", "Rejected"):
        raise HTTPException(status_code=400, detail="status must be Approved or Rejected")

    e = _load_for_update(db, expense_id)
    if e.status == "In Progress":
        raise HTTPException(status_code=400, detail="That trip has not been submitted yet")

    comment = (payload.reason or "").strip()
    now = utcnow()
    for k, v in _decision_values(current_user, payload.status, comment, now).items():
        setattr(e, k, v)
    # the comment for either outcome is kept in the activity history
    _push_history(e, current_user.display_name, f"{payload.status} by {current_user.role}", comment, at=now)

    db.commit()
    return json_response(expense_from_orm(e))


@router.post("/bulk-decide")
def bulk_decide(
    payload: BulkDecisionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_approver),
):
    """
    Set-based: one SELECT for the eligible ids, one UPDATE, one multi-row INSERT
    for the history — the same three statements for 2 requests or 200, and
    no request data (or photos) is loaded at all.
    """
    if payload.status not in ("Approved", "Rejected"):
        raise HTTPException(status_code=400, detail="status must be Approved or Rejected")
    if not payload.ids:
        return {"updated": 0}

    eligible = (E.id.in_(payload.ids), E.status != "In Progress")
    ids = db.execute(select(E.id).where(*eligible)).scalars().all()
    if not ids:
        return {"updated": 0}

    comment = (payload.reason or "").strip()
    now = utcnow()
    db.execute(
        update(E).where(E.id.in_(ids), E.status != "In Progress")
        .values(**_decision_values(current_user, payload.status, comment, now))
        .execution_options(synchronize_session=False)
    )
    action = f"{payload.status} in bulk by {current_user.role}"
    db.execute(insert(H), [
        {"expense_id": i, "at": now, "by": current_user.display_name, "action": action, "note": comment}
        for i in ids
    ])
    db.commit()
    return {"updated": len(ids)}


@router.delete("/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    row = db.execute(select(E.id, E.employee_id, E.status).where(E.id == expense_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Expense not found")
    if row.employee_id != current_user.username:
        raise HTTPException(status_code=403, detail="You can only delete your own expenses")
    if row.status == "Approved":
        raise HTTPException(status_code=400, detail="Approved expenses cannot be deleted")

    # Same outcome as the old ORM delete: uploaded files are kept but unlinked,
    # and history rows go first (whether or not the database enforces ON DELETE CASCADE).
    db.query(models.FileAsset).filter(models.FileAsset.expense_id == expense_id).update(
        {models.FileAsset.expense_id: None}, synchronize_session=False
    )
    db.query(H).filter(H.expense_id == expense_id).delete(synchronize_session=False)
    db.query(E).filter(E.id == expense_id).delete(synchronize_session=False)
    db.commit()
    return {"deleted": True}
