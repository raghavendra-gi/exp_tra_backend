"""
Live trip tracking.

While a Regional Trip is "In Progress" the employee's phone sends GPS points here.
Accounts and the Operation Head can see where each active trip is right now and the
route travelled so far. The Chairman never gets location data (same rule as expenses.py).

  POST /api/tracking/pings                 employee/clerk   - upload a batch of points
  GET  /api/tracking/active                employee/clerk   - which of MY trips should be tracked now
  GET  /api/tracking/live                  accounts/op_head - every active trip + its latest point
  GET  /api/tracking/trips/{id}/path       accounts/op_head - the whole route of one trip

Design notes
  * Points are batched by the phone, so one request carries many points (max 200).
  * The phone may be offline for a while and send old points later. Points are accepted
    if they were recorded DURING the trip (between its start and its end), for up to
    48 hours after the trip ended. Anything else is ignored.
  * Sending the same batch twice is safe: points already stored are skipped.
"""
import logging
import math
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import models
from config import settings
from deps import CurrentUser, get_current_user, get_db
from roles import ACCOUNTS, FILER_ROLES, OP_HEAD
from routers.expenses import TWO_STAGE_TYPES
from timeutil import as_utc, utcnow

router = APIRouter()
log = logging.getLogger("uvicorn.error")

E = models.Expense
H = models.ExpenseHistory
P = models.LocationPing

TRACKED_TYPES = set(TWO_STAGE_TYPES)               # trips that go In Progress -> Pending
TRIP_ENDED_ACTION = "Trip ended and submitted for approval"
TRACKING_STARTED_ACTION = "Live location tracking started"

MAX_BATCH = 200                                    # points per request
MAX_ACCURACY_M = 1000                              # worse fixes are cell-tower guesses: ignore
LATE_UPLOAD_HOURS = 48                             # how long after a trip ended old points are still taken
CLOCK_SKEW = timedelta(minutes=5)
MAX_PATH_POINTS = 3000                             # a longer route is thinned out for the map
VIEWER_ROLES = (ACCOUNTS, OP_HEAD)                 # NOT the chairman


# ───────────────────────── helpers ─────────────────────────

def _iso(dt: datetime) -> str:
    """UTC with an explicit 'Z', like every other date the API sends."""
    return as_utc(dt).isoformat().replace("+00:00", "Z")


def _naive_utc(dt: datetime) -> datetime:
    """What the database stores: UTC, no tzinfo, millisecond precision (so retries match)."""
    return as_utc(dt).replace(tzinfo=None, microsecond=(dt.microsecond // 1000) * 1000)


def require_filer(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role not in FILER_ROLES:
        raise HTTPException(status_code=403, detail="Only employees and clerks send their location")
    return user


def require_viewer(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role not in VIEWER_ROLES:
        raise HTTPException(status_code=403, detail="You do not have access to live tracking")
    return user


def _haversine_m(lat1, lng1, lat2, lng2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _trip_end(db: Session, expense_id: int) -> Optional[datetime]:
    row = (db.query(H.at)
           .filter(H.expense_id == expense_id, H.action == TRIP_ENDED_ACTION)
           .order_by(H.at.desc()).first())
    return row[0] if row else None


# ───────────────────────── schemas ─────────────────────────

class PingIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    speed: Optional[float] = Field(default=None, ge=0, le=1000)
    at: datetime                                   # when the phone measured it


class PingBatch(BaseModel):
    expense_id: int
    points: list[PingIn] = Field(min_length=1, max_length=MAX_BATCH)


# ───────────────────────── employee side ─────────────────────────

@router.post("/pings")
def upload_pings(
    payload: PingBatch,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_filer),
):
    e = db.get(E, payload.expense_id)
    if e is None or e.employee_id != user.username or e.type not in TRACKED_TYPES:
        raise HTTPException(status_code=404, detail="Trip not found")

    now = utcnow()
    in_progress = e.status == "In Progress"
    if in_progress:
        window_end = now + CLOCK_SKEW
    else:
        ended = _trip_end(db, e.id)
        # Not tracked any more: trip not ended through the normal flow, or too long ago.
        if ended is None or now > ended + timedelta(hours=LATE_UPLOAD_HOURS):
            return {"saved": 0, "skipped": len(payload.points), "active": False}
        window_end = ended + CLOCK_SKEW
    window_start = (e.created_date or now) - CLOCK_SKEW

    # Keep only sensible points recorded inside the trip's time window, once each.
    wanted: dict[datetime, PingIn] = {}
    for p in payload.points:
        at = _naive_utc(p.at)
        if not (window_start <= at <= window_end):
            continue
        if p.accuracy is not None and p.accuracy > MAX_ACCURACY_M:
            continue
        wanted.setdefault(at, p)

    saved = 0
    if wanted:
        known = {
            r[0] for r in db.query(P.recorded_at).filter(
                P.expense_id == e.id,
                P.recorded_at >= min(wanted), P.recorded_at <= max(wanted),
            ).all()
        }
        first_ever = db.query(P.id).filter(P.expense_id == e.id).first() is None
        rows = [
            dict(expense_id=e.id, employee_id=user.username, lat=p.lat, lng=p.lng,
                 accuracy=p.accuracy, speed=p.speed, recorded_at=at, received_at=now)
            for at, p in wanted.items() if at not in known
        ]
        if rows:
            db.execute(insert(P), rows)
            if first_ever:          # a visible audit line: the trip's history shows tracking began
                db.add(H(expense_id=e.id, by=user.display_name, action=TRACKING_STARTED_ACTION, at=now))
            db.commit()
            saved = len(rows)

    return {"saved": saved, "skipped": len(payload.points) - saved, "active": in_progress}


@router.get("/active")
def my_active_trips(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_filer),
):
    """The trips of the signed-in person that are In Progress, i.e. the ones to track right now."""
    rows = (db.query(E.id, E.type, E.created_date)
            .filter(E.employee_id == user.username, E.status == "In Progress", E.type.in_(TRACKED_TYPES))
            .order_by(E.created_date.desc()).all())
    return {"trips": [{"id": r.id, "type": r.type, "started_at": _iso(r.created_date)} for r in rows]}


# ───────────────────────── approver side ─────────────────────────

@router.get("/live")
def live(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_viewer),
):
    """Every active trip with its most recent point (null until the phone sends the first one)."""
    now = utcnow()
    trips = (db.query(E.id, E.employee_id, E.employee_name, E.type, E.created_date, E.data_lite)
             .filter(E.status == "In Progress", E.type.in_(TRACKED_TYPES))
             .order_by(E.created_date.desc()).all())
    ids = [t.id for t in trips]

    last: dict[int, models.LocationPing] = {}
    count: dict[int, int] = {}
    if ids:
        newest = (db.query(P.expense_id.label("eid"), func.max(P.recorded_at).label("mx"))
                  .filter(P.expense_id.in_(ids)).group_by(P.expense_id).subquery())
        for p in (db.query(P).join(newest, and_(P.expense_id == newest.c.eid, P.recorded_at == newest.c.mx)).all()):
            last[p.expense_id] = p
        count = dict(db.query(P.expense_id, func.count(P.id))
                     .filter(P.expense_id.in_(ids)).group_by(P.expense_id).all())

    out = []
    for t in trips:
        p = last.get(t.id)
        data = t.data_lite if isinstance(t.data_lite, dict) else {}
        out.append({
            "expense_id": t.id,
            "employee_id": t.employee_id,
            "employee_name": t.employee_name,
            "type": t.type,
            "started_at": _iso(t.created_date),
            "from": data.get("startLocation") or "",
            "points": count.get(t.id, 0),
            "last": None if p is None else {
                "lat": p.lat, "lng": p.lng, "accuracy": p.accuracy, "speed": p.speed,
                "at": _iso(p.recorded_at),
                "age_seconds": max(0, int((now - p.recorded_at).total_seconds())),
            },
        })
    return {"server_time": _iso(now), "trips": out}


@router.get("/trips/{expense_id}/path")
def trip_path(
    expense_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_viewer),
):
    """The route of one trip (active or finished), oldest point first, plus an approximate distance."""
    e = db.query(E.id, E.employee_name, E.type, E.status, E.created_date).filter(E.id == expense_id).first()
    if e is None or e.type not in TRACKED_TYPES:
        raise HTTPException(status_code=404, detail="Trip not found")

    rows = (db.query(P.lat, P.lng, P.accuracy, P.recorded_at)
            .filter(P.expense_id == expense_id).order_by(P.recorded_at, P.id).all())

    # Approximate distance: ignore GPS jitter (< 10 m between fixes) and impossible jumps (> 200 km/h).
    metres, prev = 0.0, None
    for r in rows:
        if r.accuracy is not None and r.accuracy > 100:
            continue
        if prev is not None:
            d = _haversine_m(prev.lat, prev.lng, r.lat, r.lng)
            dt = max(1.0, (r.recorded_at - prev.recorded_at).total_seconds())
            if d >= 10 and d / dt <= 200 / 3.6:
                metres += d
        prev = r

    total = len(rows)
    if total > MAX_PATH_POINTS:                    # thin out, but always keep the first and last point
        step = math.ceil(total / MAX_PATH_POINTS)
        rows = rows[::step] + ([rows[-1]] if (total - 1) % step else [])

    return {
        "expense_id": e.id,
        "employee_name": e.employee_name,
        "type": e.type,
        "status": e.status,
        "started_at": _iso(e.created_date),
        "count": total,
        "distance_km": round(metres / 1000, 2),
        "points": [{"lat": r.lat, "lng": r.lng, "accuracy": r.accuracy, "at": _iso(r.recorded_at)} for r in rows],
    }


# ───────────────────────── housekeeping ─────────────────────────

def purge_old_pings(db: Session, days: Optional[int] = None) -> int:
    """Delete points older than the retention period (TRACKING_RETENTION_DAYS, default 60)."""
    days = settings.tracking_retention_days if days is None else days
    if days <= 0:
        return 0
    cutoff = utcnow() - timedelta(days=days)
    try:
        n = db.query(P).filter(P.recorded_at < cutoff).delete(synchronize_session=False)
        db.commit()
    except SQLAlchemyError as exc:
        # Housekeeping must never stop the server from starting (e.g. migration 0007 was not applied yet).
        db.rollback()
        log.warning("[tracking] could not delete old GPS points (is migration 0007 applied?): %s", type(exc).__name__)
        return 0
    if n:
        log.info("[tracking] deleted %d GPS points older than %d days", n, days)
    return n
