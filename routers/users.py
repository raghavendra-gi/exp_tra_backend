from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from security import hash_password
from deps import get_db, get_current_user, CurrentUser, clear_user_cache 
import models
from schemas import UserOut, ProfileUpdate, UserCreate

router = APIRouter()

# 👇 THIS WAS MISSING 👇
@router.post("/", response_model=UserOut)
def create_employee(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
        # Only Accounts team can create employees or heads
    if current_user.role != "accounts":
        raise HTTPException(status_code=403, detail="Only Accounts team can create new employees or clerks")

        username = data.username.strip()
    email = (data.email or "").strip() or None   # blank email -> None

    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    if email and db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create the new user
    new_user = models.User(
        username=username,
        password_hash=hash_password(data.password),
        display_name=data.display_name.strip(),
        role=data.role,
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
    current_user: CurrentUser = Depends(get_current_user)
):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.username is not None: 
        existing = db.query(models.User).filter(models.User.username == data.username, models.User.id != user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")
        user.username = data.username
        
    if data.email is not None: user.email = data.email
    if data.branch is not None: user.branch = data.branch
    if data.designation is not None: user.designation = data.designation
    if data.avatar is not None: user.avatar = data.avatar

    db.commit()
    db.refresh(user)
    clear_user_cache()

    return user