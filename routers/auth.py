from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from deps import get_db, get_current_user
from security import verify_password, create_access_token, hash_password
from schemas import LoginRequest, TokenResponse, UserOut
import models

router = APIRouter()


@router.post("/register", response_model=UserOut)
def register(payload: LoginRequest, db: Session = Depends(get_db)):
    existing_user = (
        db.query(models.User)
        .filter(models.User.username == payload.username)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Username already exists"
        )

    user = models.User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role="employee",
        display_name=payload.username
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return UserOut.model_validate(user)

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    token = create_access_token({"sub": user.username, "role": user.role})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user
