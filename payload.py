"""
Fast JSON output for expenses.

The expense list is the busiest endpoint. Building a Pydantic model per row and
then having FastAPI validate it again costs more than the database query
itself, so expenses are turned into plain dicts here and encoded with orjson.
The JSON is exactly what ExpenseOut produces (tests/test_api.py checks this):
datetimes are UTC with a trailing "Z".
"""
import hashlib
from typing import Iterable, Optional

import orjson
from fastapi import Request
from fastapi.responses import Response

_OPTS = orjson.OPT_NAIVE_UTC | orjson.OPT_UTC_Z   # naive DB datetimes are UTC -> "...Z"


def strip_file_payloads(data):
    """
    Copy of `data` without the base64 `dataUrl` of each attachment
    (name / type / size / id are kept). Stored as expenses.data_lite.
    """
    if not isinstance(data, dict):
        return data
    out = {}
    for k, v in data.items():
        if isinstance(v, list) and any(isinstance(i, dict) and "dataUrl" in i for i in v):
            out[k] = [
                {kk: vv for kk, vv in i.items() if kk != "dataUrl"} if isinstance(i, dict) else i
                for i in v
            ]
        else:
            out[k] = v
    return out


def history_dict(h) -> dict:
    return {"id": h.id, "at": h.at, "by": h.by, "action": h.action, "note": h.note}


def expense_dict(e, data, history: Iterable) -> dict:
    """`e` is an Expense or a row with the same attribute names."""
    return {
        "id": e.id,
        "employee_id": e.employee_id,
        "employee_name": e.employee_name,
        "type": e.type,
        "data": data if data is not None else {},
        "status": e.status,
        "created_date": e.created_date,
        "submitted_date": e.submitted_date,
        "decided_by": e.decided_by,
        "decided_by_role": e.decided_by_role,
        "decided_date": e.decided_date,
        "rejection_reason": e.rejection_reason,
        "history": list(history),
    }


def expense_from_orm(e) -> dict:
    """Full expense (with attachments) from a loaded Expense object."""
    return expense_dict(e, e.data, (history_dict(h) for h in e.history))


def json_response(content, request: Optional[Request] = None, status_code: int = 200) -> Response:
    """
    orjson-encoded response. When `request` is given, the response carries an
    ETag and a request that already has this exact body (If-None-Match) gets an
    empty 304 — the browser then reuses its copy instead of downloading again.
    """
    body = orjson.dumps(content, option=_OPTS)
    if request is None:
        return Response(body, status_code=status_code, media_type="application/json")

    etag = '"' + hashlib.blake2b(body, digest_size=16).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache", "Vary": "Authorization"}
    match = request.headers.get("if-none-match", "")
    if etag in {t.strip() for t in match.split(",")} or match.strip() == "*":
        return Response(status_code=304, headers=headers)
    return Response(body, status_code=status_code, media_type="application/json", headers=headers)
