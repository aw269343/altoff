# -*- coding: utf-8 -*-
"""User management router with RBAC. Supports roles: admin, manager, packer, warehouseman."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.auth import get_current_user, hash_password

router = APIRouter(prefix="/api/users", tags=["users"])

# Valid roles for the system
VALID_ROLES = ("manager", "packer", "warehouseman")


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    full_name: Optional[str] = None
    created_at: Optional[str] = None


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str  # "manager" | "packer" | "warehouseman"
    full_name: Optional[str] = None


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None


@router.get("", response_model=List[UserOut])
def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List users. Admin and Manager can view."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    users = db.query(User).order_by(User.role, User.username).all()
    return [
        UserOut(
            id=u.id,
            username=u.username,
            role=u.role,
            full_name=u.full_name,
            created_at=u.created_at.strftime("%d.%m.%Y %H:%M") if u.created_at else None,
        )
        for u in users
    ]


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: CreateUserRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create user. Admin and Manager can create packer / warehouseman / manager."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Роль должна быть одной из: {', '.join(VALID_ROLES)}"
        )

    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Пользователь '{body.username}' уже существует")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        full_name=body.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role,
        full_name=user.full_name,
        created_at=user.created_at.strftime("%d.%m.%Y %H:%M") if user.created_at else None,
    )


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UpdateUserRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update user fields (full_name, role). Admin and Manager."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        if body.role not in VALID_ROLES and body.role != "admin":
            raise HTTPException(status_code=400, detail="Некорректная роль")
        user.role = body.role

    db.commit()
    db.refresh(user)
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role,
        full_name=user.full_name,
        created_at=user.created_at.strftime("%d.%m.%Y %H:%M") if user.created_at else None,
    )


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete user. Admin and Manager."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

    db.delete(user)
    db.commit()
    return {"status": "ok", "message": f"Пользователь '{user.username}' удалён"}
