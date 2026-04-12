# -*- coding: utf-8 -*-
"""Analytics router: KPI metrics for packers, warehousemen, and shift summaries."""

import os
from datetime import datetime, timedelta
from urllib.parse import quote as urllib_quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.database import get_db
from app.models import (
    User, PackingLog, SupplyLog, Packed, ReceptionItem, Shipment,
)
from app.auth import get_current_user
from app.utils.excel_exporter import generate_employee_packing_report

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _get_period_start(period: str) -> datetime:
    """Calculate the start datetime for the given period."""
    now = datetime.utcnow()
    if period == "day":
        return now - timedelta(days=1)
    elif period == "week":
        return now - timedelta(weeks=1)
    elif period == "month":
        return now - timedelta(days=30)
    elif period == "all":
        return datetime(2000, 1, 1)
    return now - timedelta(days=1)


@router.get("/packer-kpi")
def get_packer_kpi(
    period: str = Query("day", regex="^(day|week|month|all)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Packer KPI: ФИО | Всего штук | Скорость (шт/час) | Ошибки.

    Speed = SUM(quantity) / SUM(duration_seconds) * 3600
    """
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    period_start = _get_period_start(period)

    results = (
        db.query(
            PackingLog.packed_by,
            func.sum(PackingLog.quantity).label("total_items"),
            func.sum(PackingLog.duration_seconds).label("total_seconds"),
            func.sum(PackingLog.is_error).label("total_errors"),
            func.count(PackingLog.id).label("total_sessions"),
        )
        .filter(
            PackingLog.created_at >= period_start,
            PackingLog.packed_by.isnot(None),
        )
        .group_by(PackingLog.packed_by)
        .all()
    )

    user_ids = [r.packed_by for r in results if r.packed_by]
    users_map = {}
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        users_map = {u.id: u for u in users}

    kpi_data = []
    for r in results:
        user = users_map.get(r.packed_by)
        full_name = user.display_name if user else f"ID:{r.packed_by}"
        total_hours = (r.total_seconds or 0) / 3600.0
        speed = round(r.total_items / total_hours, 1) if total_hours > 0 else 0

        kpi_data.append({
            "user_id": r.packed_by,
            "full_name": full_name,
            "role": user.role if user else "—",
            "total_items": r.total_items or 0,
            "total_sessions": r.total_sessions or 0,
            "speed_per_hour": speed,
            "errors": r.total_errors or 0,
            "total_hours": round(total_hours, 2),
        })

    kpi_data.sort(key=lambda x: x["speed_per_hour"], reverse=True)
    return kpi_data


@router.get("/warehouseman-kpi")
def get_warehouseman_kpi(
    period: str = Query("day", regex="^(day|week|month|all)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Warehouseman KPI: ФИО | Всего коробок | Скорость (кор/час).

    Speed = COUNT(DISTINCT box_id) / SUM(duration_seconds) * 3600
    """
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    period_start = _get_period_start(period)

    results = (
        db.query(
            SupplyLog.processed_by,
            func.count(distinct(SupplyLog.box_id)).label("total_boxes"),
            func.sum(SupplyLog.duration_seconds).label("total_seconds"),
            func.count(SupplyLog.id).label("total_actions"),
        )
        .filter(
            SupplyLog.created_at >= period_start,
            SupplyLog.processed_by.isnot(None),
        )
        .group_by(SupplyLog.processed_by)
        .all()
    )

    user_ids = [r.processed_by for r in results if r.processed_by]
    users_map = {}
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        users_map = {u.id: u for u in users}

    kpi_data = []
    for r in results:
        user = users_map.get(r.processed_by)
        full_name = user.display_name if user else f"ID:{r.processed_by}"
        total_hours = (r.total_seconds or 0) / 3600.0
        speed = round(r.total_boxes / total_hours, 1) if total_hours > 0 else 0

        kpi_data.append({
            "user_id": r.processed_by,
            "full_name": full_name,
            "role": user.role if user else "—",
            "total_boxes": r.total_boxes or 0,
            "total_actions": r.total_actions or 0,
            "speed_per_hour": speed,
            "total_hours": round(total_hours, 2),
        })

    kpi_data.sort(key=lambda x: x["speed_per_hour"], reverse=True)
    return kpi_data


@router.get("/shift-summary")
def get_shift_summary(
    hours: int = Query(12, ge=1, le=72),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Shift summary: total counts + average speeds per role."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    period_start = datetime.utcnow() - timedelta(hours=hours)

    # Packed items (from PackingLog)
    total_packed_kpi = (
        db.query(func.sum(PackingLog.quantity))
        .filter(PackingLog.created_at >= period_start)
        .scalar() or 0
    )
    # Fallback: packed from legacy Packed table
    total_packed_legacy = (
        db.query(func.count(Packed.id))
        .filter(Packed.scanned_at >= period_start)
        .scalar() or 0
    )
    total_packed = max(total_packed_kpi, total_packed_legacy)

    # Received items
    total_received = (
        db.query(func.sum(ReceptionItem.quantity))
        .filter(ReceptionItem.scanned_at >= period_start)
        .scalar() or 0
    )

    # Boxes processed
    total_boxes = (
        db.query(func.count(distinct(SupplyLog.box_id)))
        .filter(SupplyLog.created_at >= period_start)
        .scalar() or 0
    )

    # Active packers
    active_packers = (
        db.query(func.count(distinct(PackingLog.packed_by)))
        .filter(
            PackingLog.created_at >= period_start,
            PackingLog.packed_by.isnot(None),
        )
        .scalar() or 0
    )

    # Active warehousemen
    active_warehousemen = (
        db.query(func.count(distinct(SupplyLog.processed_by)))
        .filter(
            SupplyLog.created_at >= period_start,
            SupplyLog.processed_by.isnot(None),
        )
        .scalar() or 0
    )

    # Packing errors
    total_errors = (
        db.query(func.count(PackingLog.id))
        .filter(
            PackingLog.created_at >= period_start,
            PackingLog.is_error == 1,
        )
        .scalar() or 0
    )

    # ── Average speeds ──
    packer_total_seconds = (
        db.query(func.sum(PackingLog.duration_seconds))
        .filter(
            PackingLog.created_at >= period_start,
            PackingLog.duration_seconds.isnot(None),
        )
        .scalar() or 0
    )
    packer_avg_speed = 0.0
    if packer_total_seconds > 0:
        packer_avg_speed = round(
            total_packed_kpi / (packer_total_seconds / 3600.0), 1
        )

    wh_total_seconds = (
        db.query(func.sum(SupplyLog.duration_seconds))
        .filter(
            SupplyLog.created_at >= period_start,
            SupplyLog.duration_seconds.isnot(None),
        )
        .scalar() or 0
    )
    wh_avg_speed = 0.0
    if wh_total_seconds > 0:
        wh_avg_speed = round(
            total_boxes / (wh_total_seconds / 3600.0), 1
        )

    return {
        "period_hours": hours,
        "period_start": period_start.strftime("%d.%m.%Y %H:%M"),
        "period_end": datetime.utcnow().strftime("%d.%m.%Y %H:%M"),
        "total_packed": total_packed,
        "total_received": total_received,
        "total_boxes_processed": total_boxes,
        "active_packers": active_packers,
        "active_warehousemen": active_warehousemen,
        "total_errors": total_errors,
        # New KPI averages
        "avg_packer_speed": packer_avg_speed,
        "avg_warehouseman_speed": wh_avg_speed,
    }


@router.get("/employee-packing-report")
def export_employee_packing_report(
    period: str = Query("all", regex="^(day|week|month|all)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export packing logs for all employees as Excel."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    period_start = _get_period_start(period)

    logs_query = (
        db.query(
            PackingLog.id,
            User.full_name,
            User.username,
            Shipment.name.label("tz_name"),
            PackingLog.start_time,
            PackingLog.end_time,
            PackingLog.duration_seconds,
            PackingLog.barcode,
            PackingLog.quantity,
            PackingLog.plan_quantity,
        )
        .outerjoin(User, PackingLog.packed_by == User.id)
        .outerjoin(Shipment, PackingLog.reception_id == Shipment.id)
        .filter(PackingLog.created_at >= period_start)
        .order_by(PackingLog.created_at.desc())
    )

    try:
        temp_path = generate_employee_packing_report(db, logs_query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации отчёта: {e}")

    filename = f"Отчет_сотрудники_{period}.xlsx"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{urllib_quote(filename)}",
        "Access-Control-Expose-Headers": "Content-Disposition",
    }

    return FileResponse(
        temp_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
        background=BackgroundTask(os.remove, temp_path),
    )
