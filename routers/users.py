from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from deps import get_db, get_current_user
from schemas import UserOut
import models

router = APIRouter()


@router.get("", response_model=list[UserOut])
def list_employees(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Powers the 'Everyone / Emp1 / Emp2 ...' filter on the approver's view."""
    return db.query(models.User).filter(models.User.role == "employee").all()
