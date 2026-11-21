"""
fix_neon_transfer.py - stop the dashboard from downloading every bill image from the database.

    python fix_neon_transfer.py                       # searches your user folder for the backend
    python fix_neon_transfer.py "C:\\path\\to\\app"     # or give the backend's app folder

What it changes (each file is first saved as <name>.bak):
  1. routers/expenses.py - GET /api/expenses/fund (called on every dashboard load / month change)
     used to read every approved expense in full, bill images included. It now reads only the small
     `data_lite` copy (the same data without the image bytes), so one call moves a few KB, not tens of MB.
  2. migrations/versions/0005_bill_hashes.py (if present) - skips reading every expense just to fill a
     table that migration 0006 deletes straight afterwards.
Run it, then stop the backend and start it again.
"""
import os
import sys

SKIP = {"node_modules", ".git", "site-packages", "AppData", "__pycache__", "$Recycle.Bin", "Windows", ".venv", "venv"}

OLD_KEY = '''def _expense_month_key(e) -> str:
    """'YYYY-MM' of an expense, tolerant of missing / non-string dates."""
    data = e.data if isinstance(e.data, dict) else {}
    for k in ("date", "startDate", "start_date", "fromDate", "expenseDate", "tripDate"):
        v = data.get(k)
        if isinstance(v, str) and len(v) >= 7:
            return v[:7]
    return e.created_date.strftime("%Y-%m") if e.created_date else ""
'''
NEW_KEY = '''def _month_key(data, created_date) -> str:
    """'YYYY-MM' of an expense, tolerant of missing / non-string dates."""
    data = data if isinstance(data, dict) else {}
    for k in ("date", "startDate", "start_date", "fromDate", "expenseDate", "tripDate"):
        v = data.get(k)
        if isinstance(v, str) and len(v) >= 7:
            return v[:7]
    return created_date.strftime("%Y-%m") if created_date else ""


def _expense_month_key(e) -> str:
    return _month_key(e.data, e.created_date)
'''

OLD_FUND = '''    exp_q = db.query(models.Expense).filter(models.Expense.status == "Approved")
    if target:
        fund_q = fund_q.filter(models.MonthlyFund.employee_id == target)
        exp_q = exp_q.filter(models.Expense.employee_id == target)

    total_fund = float(sum(f.amount or 0.0 for f in fund_q.all()))

    month_str = f"{year}-{month:02d}"
    spent_amount = 0.0
    for e in exp_q.all():
        if _expense_month_key(e) == month_str:
            spent_amount += _amount(e.data)
'''
NEW_FUND = '''    # Read only the small data_lite copy (no bill images). Loading whole expenses here made every
    # dashboard visit download all approved bills from the database.
    exp_stmt = select(E.id, E.created_date, E.data_lite).where(E.status == "Approved")
    if target:
        fund_q = fund_q.filter(models.MonthlyFund.employee_id == target)
        exp_stmt = exp_stmt.where(E.employee_id == target)

    total_fund = float(sum(f.amount or 0.0 for f in fund_q.all()))

    month_str = f"{year}-{month:02d}"
    spent_amount = 0.0
    rows = db.execute(exp_stmt).all()
    missing = [r.id for r in rows if r.data_lite is None]          # rows saved before data_lite existed
    full = dict(db.execute(select(E.id, E.data).where(E.id.in_(missing))).all()) if missing else {}
    for r in rows:
        data = full.get(r.id, r.data_lite)
        if _month_key(data, r.created_date) == month_str:
            spent_amount += _amount(data)
'''

OLD_BACKFILL = '''    if op.get_context().as_sql:
        return   # `--sql`: no rows to read
'''
NEW_BACKFILL = '''    # Nothing to fill in: migration 0006 drops this table right away, so reading every expense
    # (with its bill images) over the network would only waste database transfer.
    return
'''


def is_app_folder(path):
    return os.path.isfile(os.path.join(path, "main.py")) and os.path.isfile(os.path.join(path, "routers", "expenses.py"))


def find_apps(root):
    for folder, dirs, _f in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP]
        if is_app_folder(folder):
            yield folder
            dirs[:] = []


def patch(path, pairs, label):
    with open(path, "rb") as fh:
        raw = fh.read()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if all(new in text for _o, new in pairs):
        print("   already fixed :", label)
        return
    for old, _new in pairs:
        if old not in text:
            print("   NOT PATCHED   :", label, "(this file differs from what I expected - send it to me)")
            return
    for old, new in pairs:
        text = text.replace(old, new, 1)
    if crlf:
        text = text.replace("\n", "\r\n")
    with open(path + ".bak", "wb") as fh:
        fh.write(raw)
    with open(path, "wb") as fh:
        fh.write(text.encode("utf-8"))
    print("   FIXED         :", label)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~")
    apps = [target] if is_app_folder(target) else list(find_apps(target))
    if not apps:
        print("Could not find the backend. Run again with the folder that contains main.py.")
        return
    for app in apps:
        print("Backend:", app)
        patch(os.path.join(app, "routers", "expenses.py"), [(OLD_KEY, NEW_KEY), (OLD_FUND, NEW_FUND)], "routers/expenses.py (fund query)")
        mig = os.path.join(app, "migrations", "versions", "0005_bill_hashes.py")
        if os.path.exists(mig):
            patch(mig, [(OLD_BACKFILL, NEW_BACKFILL)], "migrations/versions/0005_bill_hashes.py")
    print("\nNow stop the backend (Ctrl+C) and start it again:  python -m uvicorn main:app")


if __name__ == "__main__":
    main()