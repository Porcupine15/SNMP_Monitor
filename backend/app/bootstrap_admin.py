"""Create the first administrator without exposing public registration."""

import argparse
import getpass
import os

from app.auth import get_password_hash
from app.database import SessionLocal
from app.models import User
from app.schemas import UserCreate


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first SNMP Monitor administrator")
    parser.add_argument("--username", required=True)
    parser.add_argument("--email")
    args = parser.parse_args()

    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass("Administrator password: ")
        confirmation = getpass.getpass("Repeat password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match")

    data = UserCreate(username=args.username, password=password, email=args.email)
    db = SessionLocal()
    try:
        if db.query(User).count():
            raise SystemExit("Users already exist; create additional accounts from the admin interface")
        user = User(
            username=data.username,
            email=data.email,
            hashed_password=get_password_hash(data.password),
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"Administrator {user.username!r} created")
    finally:
        db.close()


if __name__ == "__main__":
    main()
