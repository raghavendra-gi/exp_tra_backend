from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from deps import get_db, get_current_user, CurrentUser
from security import verify_password, create_access_token
from schemas import LoginRequest, TokenResponse, UserOut
import models

router = APIRouter()

# NOTE: the public /register endpoint was removed. It let anyone on the internet create
# an employee account. Users are now created only by the Accounts team (POST /api/users).


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    # Letter case is ignored ("Accounts" == "accounts"). The token keeps the stored spelling.
    uname = payload.username.strip().lower()
    user = db.query(models.User).filter(func.lower(models.User.username) == uname).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    token = create_access_token({"sub": user.username, "role": user.role})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: CurrentUser = Depends(get_current_user)):
    return current_user