"""
Quick utility to reset or create the admin account password.
"""
from app.models import SessionLocal, init_db, engine
from app.models.entities import User
from argon2 import PasswordHasher

def reset_admin(username="admin", password="admin"):
    init_db()
    db = SessionLocal()
    try:
        ph = PasswordHasher()
        u = db.query(User).filter_by(username=username).first()
        if u:
            u.password_hash = ph.hash(password)
            u.is_active = True
            u.role = "admin"
            db.commit()
            print(f"SUCCESS: Password for user '{username}' has been updated to '{password}'.")
        else:
            u = User(
                username=username,
                password_hash=ph.hash(password),
                role="admin",
                is_active=True
            )
            db.add(u)
            db.commit()
            print(f"SUCCESS: User '{username}' created with password '{password}'.")

        users = [x.username for x in db.query(User).all()]
        print(f"Database Engine: {engine.url}")
        print(f"Active Users in Database: {users}")
    finally:
        db.close()

if __name__ == "__main__":
    reset_admin()
