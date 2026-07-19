import os
from queue import Queue
from threading import Barrier, Thread

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User
from app.routes.admin import update_user_role, update_user_status
from app.schemas import UserRoleUpdate, UserStatusUpdate


POSTGRES_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")


@pytest.mark.skipif(
    not POSTGRES_TEST_DATABASE_URL,
    reason="POSTGRES_TEST_DATABASE_URL is required for the locking integration test",
)
def test_concurrent_admin_changes_leave_one_active_administrator():
    engine = create_engine(POSTGRES_TEST_DATABASE_URL, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine)
    setup_db = testing_session()
    try:
        primary = User(
            username="postgres-primary",
            hashed_password="test-hash",
            role="admin",
            is_active=True,
        )
        secondary = User(
            username="postgres-secondary",
            hashed_password="test-hash",
            role="admin",
            is_active=True,
        )
        setup_db.add_all([primary, secondary])
        setup_db.commit()
        primary_id = primary.id
        secondary_id = secondary.id
    finally:
        setup_db.close()

    start = Barrier(2)
    outcomes: Queue[str] = Queue()

    def disable_secondary() -> None:
        db = testing_session()
        try:
            actor = db.get(User, primary_id)
            start.wait(timeout=5)
            update_user_status(
                user_id=secondary_id,
                data=UserStatusUpdate(is_active=False),
                db=db,
                current_user=actor,
            )
            outcomes.put("success")
        except HTTPException as exc:
            db.rollback()
            outcomes.put(f"http-{exc.status_code}")
        finally:
            db.close()

    def demote_primary() -> None:
        db = testing_session()
        try:
            actor = db.get(User, secondary_id)
            start.wait(timeout=5)
            update_user_role(
                user_id=primary_id,
                data=UserRoleUpdate(role="viewer"),
                db=db,
                current_user=actor,
            )
            outcomes.put("success")
        except HTTPException as exc:
            db.rollback()
            outcomes.put(f"http-{exc.status_code}")
        finally:
            db.close()

    threads = [Thread(target=disable_secondary), Thread(target=demote_primary)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted([outcomes.get_nowait(), outcomes.get_nowait()]) == [
        "http-400",
        "success",
    ]

    verify_db = testing_session()
    try:
        active_admins = verify_db.query(User).filter_by(
            role="admin",
            is_active=True,
        ).all()
        assert len(active_admins) == 1
    finally:
        verify_db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
