import logging
import threading
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, ExpiredSignatureError

from database import SessionLocal
from security import decode_access_token
import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Messages go to the uvicorn terminal so you can see WHY a request got a 401.
log = logging.getLogger("uvicorn.error")


# The signed-in user is looked up on every request. That lookup is cached in
# memory for a short time so most requests skip a database round trip
# (/auth/me needs none at all). A role or name change shows up within
# USER_CACHE_SECONDS; a deleted user is rejected again within the same time.
USER_CACHE_SECONDS = 60


@dataclass(frozen=True)
class CurrentUser:
    """What the routes use from the signed-in user (same attribute names as models.User)."""
    id: int
    username: str
    role: str
    display_name: str


_user_cache: dict = {}
_user_cache_lock = threading.Lock()


def clear_user_cache():
    with _user_cache_lock:
        _user_cache.clear()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _unauthorized(detail: str, reason: str) -> HTTPException:
    """Build the 401 and write the real reason to the server log."""
    log.warning("401 Unauthorized -> %s", reason)
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> CurrentUser:
    try:
        payload = decode_access_token(token)
    except ExpiredSignatureError:
        # The most common case: the page was left open longer than
        # ACCESS_TOKEN_EXPIRE_MINUTES. Safe and useful to tell the client.
        raise _unauthorized("Session expired. Please sign in again.", "token expired")
    except JWTError as exc:
        # bad signature (different SECRET_KEY), malformed token, "undefined", ...
        raise _unauthorized("Could not validate credentials", f"invalid token ({exc})")

    username = payload.get("sub")
    if not username:
        raise _unauthorized("Could not validate credentials", "token has no 'sub' claim")

    now = time.monotonic()
    hit = _user_cache.get(username)
    if hit and hit[0] > now:
        return hit[1]

    row = db.query(models.User.id, models.User.username, models.User.role, models.User.display_name) \
        .filter(models.User.username == username).first()
    if row is None:
        # Token is genuine but this database has no such user
        # (DATABASE_URL was switched, DB recreated, user deleted ...)
        raise _unauthorized(
            "Could not validate credentials",
            f"user '{username}' from the token does not exist in the connected database",
        )
    user = CurrentUser(row.id, row.username, row.role, row.display_name)
    with _user_cache_lock:
        if len(_user_cache) > 5000:
            _user_cache.clear()
        _user_cache[username] = (now + USER_CACHE_SECONDS, user)
    return user


def require_approver(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """head or hr only - matches canApprove() in the frontend."""
    if user.role not in ("head", "hr"):
        raise HTTPException(status_code=403, detail="Approver role required")
    return user
