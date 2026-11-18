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

CHAIRMAN = "chairman" 

# Who can approve / reject an expense.

APPROVER_ROLES: tuple[str, ...] = (ACCOUNTS, OP_HEAD, CHAIRMAN)



# Who can file bills: employees and clerks.

FILER_ROLES: tuple[str, ...] = (EMPLOYEE, CLERK)



# Every role that is allowed to exist on a user account.

ALLOWED_ROLES: tuple[str, ...] = (EMPLOYEE, CLERK, ACCOUNTS, OP_HEAD, CHAIRMAN)



# Human-friendly labels (frontend, PDF exports, history rendering, …).

ROLE_LABELS: dict[str, str] = {

    EMPLOYEE: "Employee",

    CLERK:    "Clerk",

    ACCOUNTS: "Accounts",

    OP_HEAD:  "Operation Head",
    
    CHAIRMAN: "Chairman", 
}



# Kept only so you can explicitly reject old names with a clear error.

RETIRED_ROLES: dict[str, str] = {

    "hr":   ACCOUNTS,

    "head": CLERK,

}


# ── Custom role labels ────────────────────────────────────────────────────────
# Accounts can give a person a label that is not one of the built-in roles (for example
# "Area Manager"). It is only a label: the person keeps plain Employee access.
MAX_ROLE_TITLE = 50


def _squash(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


# Same comparison the Create Employee page makes, so a label cannot pose as a built-in role.
_BUILTIN_NAMES = {_squash(n) for n in (*ALLOWED_ROLES, *ROLE_LABELS.values(), "Operational Head")}


def clean_role_title(value):
    """Tidy a typed role label. '' / None -> None. Raises ValueError for an unusable label."""
    title = " ".join(str(value or "").split())
    if not title:
        return None
    if len(title) > MAX_ROLE_TITLE:
        raise ValueError(f"The role name must be {MAX_ROLE_TITLE} characters or fewer")
    if _squash(title) in _BUILTIN_NAMES:
        raise ValueError("That role already exists. Choose it from the Role list")
    return title
