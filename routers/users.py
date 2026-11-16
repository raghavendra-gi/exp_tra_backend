from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from security import hash_password
from deps import get_db, get_current_user, CurrentUser, clear_user_cache
import models
from roles import EMPLOYEE
from schemas import UserOut, ProfileUpdate, UserCreate, UserAdminOut, UserAdminUpdate

router = APIRouter()


# Both paths are registered so "/api/users" and "/api/users/" work. Without this, a call
# to the other form is answered with a redirect, which browsers can block on a deployed site.
@router.post("", response_model=UserOut)
@router.post("/", response_model=UserOut, include_in_schema=False)
def create_employee(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    # Only the Accounts team can create users
    if current_user.role != "accounts":
        raise HTTPException(status_code=403, detail="Only Accounts team can create new users")

    username = data.username.strip()
    display_name = data.display_name.strip()
    email = (data.email or "").strip() or None   # blank email -> None (the column is unique)

    if not username or not display_name or not data.password:
        raise HTTPException(status_code=400, detail="Username, password and display name are required")

    # "Accounts" and "accounts" must not both exist, because login ignores letter case.
    if db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    if email and db.query(models.User).filter(func.lower(models.User.email) == email.lower()).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = models.User(
        username=username,
        password_hash=hash_password(data.password),
        display_name=display_name,
        role=data.role,                       # already limited to the 4 valid roles by UserCreate
        role_title=data.role_title if data.role == EMPLOYEE else None,   # a typed label only goes with Employee access
        email=email,
        branch=(data.branch or "").strip() or None,
        designation=(data.designation or "").strip() or None,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    clear_user_cache()

    return new_user


@router.put("/profile", response_model=UserOut)
def update_profile(
    data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.email is not None:
        email = data.email.strip() or None
        if email and db.query(models.User).filter(
            func.lower(models.User.email) == email.lower(), models.User.id != user.id
        ).first():
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = email

    if data.branch is not None:
        user.branch = data.branch.strip() or None
    if data.designation is not None:
        user.designation = data.designation.strip() or None
    if data.avatar is not None:
        user.avatar = data.avatar

    db.commit()
    db.refresh(user)
    clear_user_cache()

    return user


# ───────── Accounts: see and edit every user ─────────
def _only_accounts(current_user: CurrentUser) -> None:
    if current_user.role != "accounts":
        raise HTTPException(status_code=403, detail="Only the Accounts team can manage users")


@router.get("", response_model=list[UserAdminOut])
@router.get("/", response_model=list[UserAdminOut], include_in_schema=False)
def list_users(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Everyone who can sign in, so the Accounts team always sees their current details."""
    _only_accounts(current_user)
    cols = (
        models.User.id, models.User.username, models.User.display_name, models.User.role,
        models.User.role_title, models.User.email, models.User.branch, models.User.designation,
        models.User.created_at,
    )   # not the avatar: it is a large image and the list does not show it
    rows = db.query(*cols).order_by(func.lower(models.User.display_name), models.User.id).all()
    return [UserAdminOut.model_validate(r._mapping) for r in rows]


@router.put("/{user_id}", response_model=UserAdminOut)
def update_user(
    user_id: int,
    data: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Accounts edits another person's details, role or password.
    The username stays as it is: it is the login name, it is stored inside the sign-in token
    and expenses.employee_id points at it.
    """
    _only_accounts(current_user)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sent = data.model_fields_set

    if "role" in sent and data.role is not None and data.role != user.role:
        if user.id == current_user.id:
            # Otherwise the last Accounts user could lock everybody out of this page.
            raise HTTPException(status_code=400, detail="You cannot change your own role. Ask another Accounts user.")
        user.role = data.role

    if "display_name" in sent and data.display_name is not None:
        old_name, user.display_name = user.display_name, data.display_name
        if old_name != user.display_name:
            # expenses keep a copy of the name from when they were filed: keep the lists in step
            db.query(models.Expense).filter(models.Expense.employee_id == user.username).update(
                {"employee_name": user.display_name}, synchronize_session=False)

    if "email" in sent and data.email is not None:
        email = data.email or None
        if email:
            if "@" not in email or " " in email:
                raise HTTPException(status_code=400, detail="Enter a valid email address")
            if db.query(models.User).filter(
                func.lower(models.User.email) == email.lower(), models.User.id != user.id
            ).first():
                raise HTTPException(status_code=400, detail="Email already registered")
        user.email = email

    if "branch" in sent and data.branch is not None:
        user.branch = data.branch or None
    if "designation" in sent and data.designation is not None:
        user.designation = data.designation or None

    if "role_title" in sent and data.role_title is not None:
        user.role_title = data.role_title or None
    if user.role != EMPLOYEE:
        user.role_title = None            # a typed label only goes with Employee access

    if data.new_password:
        user.password_hash = hash_password(data.new_password)

    db.commit()
    db.refresh(user)
    clear_user_cache()
    return user