from datetime import datetime, timedelta
from typing import Optional

from jose import jwt
from passlib.context import CryptContext

from config import settings


# Password hashing configuration
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


# Hash a plain-text password
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# Verify a plain-text password against the stored hash
def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


# Create JWT access token
def create_access_token(
    data: dict,
    expires_minutes: Optional[int] = None
) -> str:

    to_encode = data.copy()

    expire_minutes = (
        expires_minutes
        if expires_minutes is not None
        else settings.access_token_expire_minutes
    )

    expire = datetime.utcnow() + timedelta(minutes=expire_minutes)

    to_encode.update({
        "exp": expire
    })

    return jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm
    )


# Decode and validate JWT access token
def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.algorithm]
    )
