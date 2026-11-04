from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

# ✅ ADDED get_db TO THE IMPORT LIST HERE
from deps import get_db, get_current_user, CurrentUser, clear_user_cache 
import models
from schemas import UserOut, ProfileUpdate

router = APIRouter()

# ... (your existing routes like create_user) ...

@router.put("/profile", response_model=UserOut)
def update_profile(
    data: ProfileUpdate,
    db: Session = Depends(get_db), # Now this will work!
    current_user: CurrentUser = Depends(get_current_user)
):
    # 1. Fetch the user from the database
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Update fields if they are provided in the request
    if data.username is not None: 
        # Check if new username is already taken
        existing = db.query(models.User).filter(models.User.username == data.username, models.User.id != user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")
        user.username = data.username
        
    if data.email is not None: user.email = data.email
    if data.branch is not None: user.branch = data.branch
    if data.designation is not None: user.designation = data.designation
    if data.avatar is not None: user.avatar = data.avatar

    # 3. Save to database
    db.commit()
    db.refresh(user)
    
    # 4. Clear the dependency cache so the next /auth/me call gets the fresh data
    clear_user_cache()

    return user