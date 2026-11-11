# roles.py
"""
Central role definitions.

Role history (Nov 2026):
    "hr"   -> renamed to "accounts"
    "head" -> renamed to "clerk"
    "op_head" unchanged.
"""

EMPLOYEE = "employee"
CLERK    = "clerk"
ACCOUNTS = "accounts"
OP_HEAD  = "op_head"

# Who can approve / reject an expense.
APPROVER_ROLES: tuple[str, ...] = (CLERK, ACCOUNTS, OP_HEAD)

# Every role that is allowed to exist on a user account.
ALLOWED_ROLES: tuple[str, ...] = (EMPLOYEE, CLERK, ACCOUNTS, OP_HEAD)

# Human-friendly labels (frontend, PDF exports, history rendering, …).
ROLE_LABELS: dict[str, str] = {
    EMPLOYEE: "Employee",
    CLERK:    "Clerk",
    ACCOUNTS: "Accounts",
    OP_HEAD:  "Operation Head",
}

# Kept only so you can explicitly reject old names with a clear error.
RETIRED_ROLES: dict[str, str] = {
    "hr":   ACCOUNTS,
    "head": CLERK,
}