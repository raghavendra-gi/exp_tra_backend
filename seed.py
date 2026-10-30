from sqlalchemy.orm import Session

import models
from security import hash_password

# Same five accounts the frontend currently hardcodes in its USERS array.
# Change/rotate these passwords for anything beyond local development.
SEED_USERS = [
    {"username": "head", "password": "head@123", "role": "head", "display_name": "Head"},
    {"username": "hr", "password": "hr@123", "role": "hr", "display_name": "H.R"},
    {"username": "emp1", "password": "emp1@123", "role": "employee", "display_name": "Emp1"},
    {"username": "emp2", "password": "emp2@123", "role": "employee", "display_name": "Emp2"},
    {"username": "emp3", "password": "emp3@123", "role": "employee", "display_name": "Emp3"},
]


def seed_users(db: Session):
    if db.query(models.User).count() > 0:
        return
    for u in SEED_USERS:
        db.add(models.User(
            username=u["username"],
            password_hash=hash_password(u["password"]),
            role=u["role"],
            display_name=u["display_name"],
        ))
    db.commit()
