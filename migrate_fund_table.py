"""Run once from the backend `app` folder:  python migrate_fund_table.py

monthly_funds now has an employee_id column. create_all() will not alter an existing
table, so this drops the (test-only) old table and recreates it with the new shape.
"""
from database import Base, engine
import models

models.MonthlyFund.__table__.drop(bind=engine, checkfirst=True)
Base.metadata.create_all(bind=engine)
print("monthly_funds recreated")