from sqlalchemy.orm import Session

import models
from security import hash_password

# Same five accounts the frontend currently hardcodes in its USERS array.
# Change/rotate these passwords for anything beyond local development.
SEED_USERS = [
    {"username": "clerk", "password": "clerk@123", "role": "clerk", "display_name": "clerk"},
    {"username": "accounts", "password": "accounts@123", "role": "accounts", "display_name": "Accounts"},
    {"username": "ophead", "password": "ophead@123", "role": "op_head", "display_name": "Op Head"},
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
