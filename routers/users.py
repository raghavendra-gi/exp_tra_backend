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
    # Only HR can create employees or heads
    if current_user.role != "hr":
        raise HTTPException(status_code=403, detail="Only HR can create new employees or heads")

    # Check if username or email already exists
    existing_user = db.query(models.User).filter(
        (models.User.username == data.username) | (models.User.email == data.email)
    ).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username or email already registered")

    # Create the new user
    new_user = models.User(
        username=data.username,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
        role=data.role,
        email=data.email,
        branch=data.branch,
        designation=data.designation
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