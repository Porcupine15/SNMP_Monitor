import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import (
    create_access_token,
    get_current_user,
    get_password_hash,
    password_token_version,
    require_roles,
    verify_password,
)
from app.database import Base
from app.models import AuditEvent, User
from app.routes.admin import create_user, update_user, update_user_role, update_user_status
from app.schemas import UserAdminCreate, UserAdminUpdate, UserRoleUpdate, UserStatusUpdate


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_admin_can_create_additional_admin_and_manage_other_accounts():
    db = _session()
    primary_admin = User(
        username="primary-admin",
        hashed_password="bootstrap-hash",
        role="admin",
        is_active=True,
    )
    db.add(primary_admin)
    db.commit()

    additional_admin = create_user(
        data=UserAdminCreate(
            username="secondary-admin",
            password="secondary-admin-password",
            role="admin",
        ),
        db=db,
        current_user=primary_admin,
    )
    operator = create_user(
        data=UserAdminCreate(
            username="network-operator",
            password="network-operator-password",
            role="operator",
        ),
        db=db,
        current_user=additional_admin,
    )

    assert db.query(User).filter(User.role == "admin").count() == 2
    assert additional_admin.role == "admin"

    edited = update_user(
        user_id=operator.id,
        data=UserAdminUpdate(
            username="network-viewer",
            email="viewer@example.internal",
            password="replacement-user-password",
        ),
        db=db,
        current_user=primary_admin,
    )
    updated = update_user_role(
        user_id=operator.id,
        data=UserRoleUpdate(role="viewer"),
        db=db,
        current_user=additional_admin,
    )
    disabled = update_user_status(
        user_id=operator.id,
        data=UserStatusUpdate(is_active=False),
        db=db,
        current_user=additional_admin,
    )

    assert edited.username == "network-viewer"
    assert edited.email == "viewer@example.internal"
    assert verify_password("replacement-user-password", edited.hashed_password)
    assert updated.role == "viewer"
    assert disabled.is_active is False
    assert db.query(AuditEvent).filter_by(username="primary-admin").count() == 2
    assert db.query(AuditEvent).filter_by(username="secondary-admin").count() == 3


def test_admin_cannot_demote_or_disable_own_account():
    db = _session()
    admin = User(
        username="protected-admin",
        hashed_password="bootstrap-hash",
        role="admin",
        is_active=True,
    )
    db.add(admin)
    db.commit()

    with pytest.raises(HTTPException, match="Cannot change own role"):
        update_user_role(
            user_id=admin.id,
            data=UserRoleUpdate(role="viewer"),
            db=db,
            current_user=admin,
        )

    with pytest.raises(HTTPException, match="Cannot deactivate own account"):
        update_user_status(
            user_id=admin.id,
            data=UserStatusUpdate(is_active=False),
            db=db,
            current_user=admin,
        )

    with pytest.raises(HTTPException, match="Cannot edit own account"):
        update_user(
            user_id=admin.id,
            data=UserAdminUpdate(username="renamed-admin"),
            db=db,
            current_user=admin,
        )

    db.refresh(admin)
    assert admin.role == "admin"
    assert admin.is_active is True


def test_stale_admin_request_cannot_remove_last_active_administrator():
    db = _session()
    primary = User(
        username="concurrent-primary",
        hashed_password="bootstrap-hash",
        role="admin",
        is_active=True,
    )
    secondary = User(
        username="concurrent-secondary",
        hashed_password="bootstrap-hash",
        role="admin",
        is_active=True,
    )
    db.add_all([primary, secondary])
    db.commit()

    update_user_status(
        user_id=secondary.id,
        data=UserStatusUpdate(is_active=False),
        db=db,
        current_user=primary,
    )

    # Represents a request that passed authorization just before the actor was
    # disabled by another administrator.
    with pytest.raises(HTTPException, match="At least one active administrator"):
        update_user_role(
            user_id=primary.id,
            data=UserRoleUpdate(role="viewer"),
            db=db,
            current_user=secondary,
        )

    db.refresh(primary)
    assert primary.role == "admin"
    assert primary.is_active is True


def test_secondary_admin_resets_password_and_revokes_existing_token():
    db = _session()
    primary = User(
        username="token-primary-admin",
        email="primary@example.internal",
        hashed_password=get_password_hash("primary-admin-password"),
        role="admin",
        is_active=True,
    )
    db.add(primary)
    db.commit()

    secondary = create_user(
        data=UserAdminCreate(
            username="token-secondary-admin",
            password="secondary-admin-password",
            role="admin",
        ),
        db=db,
        current_user=primary,
    )
    operator = create_user(
        data=UserAdminCreate(
            username="token-operator",
            password="initial-operator-password",
            role="operator",
        ),
        db=db,
        current_user=secondary,
    )
    old_token = create_access_token(
        {
            "sub": operator.username,
            "pwd": password_token_version(operator.hashed_password),
        }
    )

    edited = update_user(
        user_id=operator.id,
        data=UserAdminUpdate(
            email="operator@example.internal",
            password="replacement-operator-password",
            role="viewer",
        ),
        db=db,
        current_user=secondary,
    )

    assert db.query(User).filter(User.role == "admin").count() == 2
    assert edited.email == "operator@example.internal"
    assert edited.role == "viewer"
    assert verify_password("replacement-operator-password", edited.hashed_password)

    with pytest.raises(HTTPException) as old_token_error:
        asyncio.run(get_current_user(token=old_token, db=db))
    assert old_token_error.value.status_code == 401

    new_token = create_access_token(
        {
            "sub": edited.username,
            "pwd": password_token_version(edited.hashed_password),
        }
    )
    assert asyncio.run(get_current_user(token=new_token, db=db)).id == edited.id

    admin_guard = require_roles("admin")
    with pytest.raises(HTTPException) as role_error:
        asyncio.run(admin_guard(current_user=edited))
    assert role_error.value.status_code == 403

    update_user_status(
        user_id=edited.id,
        data=UserStatusUpdate(is_active=False),
        db=db,
        current_user=secondary,
    )
    with pytest.raises(HTTPException) as disabled_token_error:
        asyncio.run(get_current_user(token=new_token, db=db))
    assert disabled_token_error.value.status_code == 401
