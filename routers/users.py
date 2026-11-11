from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from security import hash_password
from deps import get_db, get_current_user, CurrentUser, clear_user_cache
import models
from schemas import UserOut, ProfileUpdate, UserCreate

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

    # The username is NOT changeable here: it is the login name, it is stored inside the
    # sign-in token, and expenses.employee_id points at it. Changing it would sign the
    # person out with a 401 and break their expenses. Any "username" sent is ignored.

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