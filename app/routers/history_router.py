# -*- coding: utf-8 -*-
"""History router: archived shipments/receptions, reports, reopen."""

import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Shipment, Item, Packed, ReceptionItem
from app.auth import get_current_user

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/shipments")
def history_shipments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List archived shipments."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    shipments = (
        db.query(Shipment)
        .filter(Shipment.status == "archived", Shipment.type == "shipment")
        .order_by(Shipment.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": s.id,
            "name": s.name,
            "created_at": s.created_at.strftime("%d.%m.%Y") if s.created_at else "—",
        }
        for s in shipments
    ]


@router.get("/receptions")
def history_receptions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List archived receptions."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    receptions = (
        db.query(Shipment)
        .filter(Shipment.status == "archived", Shipment.type == "reception")
        .order_by(Shipment.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": s.id,
            "name": s.name,
            "created_at": s.created_at.strftime("%d.%m.%Y") if s.created_at else "—",
        }
        for s in receptions
    ]



@router.post("/{item_id}/reopen")
def reopen_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reopen archived shipment/reception. Admin and Manager only."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    shipment = db.query(Shipment).filter(Shipment.id == item_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    if shipment.status != "archived":
        raise HTTPException(status_code=400, detail="Запись не в архиве")

    shipment.status = "completed"
    db.commit()
    return {"status": "ok", "message": f"#{item_id} возвращён из архива"}
