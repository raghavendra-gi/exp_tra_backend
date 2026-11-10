from database import SessionLocal
from security import hash_password
import models

db = SessionLocal()

# 1. Print all users so we can see exactly what the backend sees
print("\n--- CURRENT USERS IN DATABASE ---")
users = db.query(models.User).all()
for u in users:
    print(f"Username: {u.username} | Role: {u.role}")
print("---------------------------------\n")

# 2. Create or Update 'clerk'
clerk = db.query(models.User).filter(models.User.username == 'clerk').first()
if clerk:
    clerk.password_hash = hash_password('clerk@123')
    print("✅ Found existing 'clerk'. Password updated to clerk@123")
else:
    print("⚠️ 'clerk' not found. Creating a new user...")
    new_clerk = models.User(
        username='clerk',
        password_hash=hash_password('clerk@123'),
        role='clerk',
        display_name='Clerk',
        email='clerk@mail.com'
    )
    db.add(new_clerk)
    print("✅ Created new 'clerk' user with password clerk@123")

# 3. Create or Update 'accounts'
accounts = db.query(models.User).filter(models.User.username == 'accounts').first()
if accounts:
    accounts.password_hash = hash_password('accounts@123')
    print("✅ Found existing 'accounts'. Password updated to accounts@123")
else:
    print("⚠️ 'accounts' not found. Creating a new user...")
    new_accounts = models.User(
        username='accounts',
        password_hash=hash_password('accounts@123'),
        role='accounts',
        display_name='Accounts',
        email='accounts@mail.com'
    )
    db.add(new_accounts)
    print("✅ Created new 'accounts' user with password accounts@123")

# Save changes to database
db.commit()
db.close()
print("\n🎉 Database sync complete! Try logging in now.")