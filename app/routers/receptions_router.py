# -*- coding: utf-8 -*-
"""Receptions router: create, scan, upload Excel, complete."""

import io
import os
import gc
from datetime import datetime
from typing import Optional
from urllib.parse import quote as urllib_quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.database import get_db
from app.models import User, Shipment, ReceptionItem, Stock, StockMovement, PackingLog
from app.auth import get_current_user
from app.utils.excel_exporter import generate_reception_report, generate_packing_report

router = APIRouter(prefix="/api/receptions", tags=["receptions"])


class CreateReceptionRequest(BaseModel):
    name: str

class PackRequest(BaseModel):
    barcode: str
    quantity: int = 1
    box_number: int = None
    start_time: str = None

class ReceptionScanRequest(BaseModel):
    barcode: str
    quantity: int = 1


@router.get("/global-task/{barcode}")
def get_global_task(
    barcode: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate plan quantities for a barcode across all active receptions."""
    items = (
        db.query(ReceptionItem, Shipment.name)
        .join(Shipment, ReceptionItem.shipment_id == Shipment.id)
        .filter(
            Shipment.status == "active",
            Shipment.type == "reception",
            ReceptionItem.barcode == barcode
        )
        .order_by(Shipment.created_at.asc())
        .all()
    )

    if not items:
        # Check if the user is scanning garbage
        raise HTTPException(status_code=404, detail=f"Артикул {barcode} не нужен ни в одной активной приёмке!")

    total_plan = sum(item.ReceptionItem.quantity for item in items)
    technical_assignments = list(set(name for _, name in items if name))

    # Calculate how much we already packed globally for these specific items
    reception_item_ids = [item.ReceptionItem.id for item in items]
    packed_qty = (
        db.query(func.sum(PackingLog.quantity))
        .filter(PackingLog.reception_item_id.in_(reception_item_ids))
        .scalar() or 0
    )

    remaining_to_pack = max(0, total_plan - packed_qty)

    # We will also pass back the list of item info just in case frontend wants it
    article_name = items[0].ReceptionItem.article or "—"
    size_name = items[0].ReceptionItem.size or "—"

    return {
        "barcode": barcode,
        "article": article_name,
        "size": size_name,
        "total_plan": total_plan,
        "total_packed": packed_qty,
        "remaining_to_pack": remaining_to_pack,
        "technical_assignments": technical_assignments,
        "tz_text": ", ".join(technical_assignments),
    }

@router.post("/global-pack")
def do_global_pack(
    body: PackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Distribute packed quantity across active receptions via FIFO."""
    if current_user.role not in ("admin", "manager", "packer"):
        raise HTTPException(status_code=403, detail="Только для упаковщиков")

    items = (
        db.query(ReceptionItem, Shipment)
        .join(Shipment, ReceptionItem.shipment_id == Shipment.id)
        .filter(
            Shipment.status == "active",
            Shipment.type == "reception",
            ReceptionItem.barcode == body.barcode
        )
        .order_by(Shipment.created_at.asc())
        .all()
    )

    if not items:
        raise HTTPException(status_code=404, detail=f"Артикул {body.barcode} не найден в приёмках!")

    # Calculate remaining needs per item
    # Since packed quantities could be anything, we must fetch existing packs
    reception_item_ids = [i.ReceptionItem.id for i in items]
    existing_packs = (
        db.query(PackingLog.reception_item_id, func.sum(PackingLog.quantity).label("p_qty"))
        .filter(PackingLog.reception_item_id.in_(reception_item_ids))
        .group_by(PackingLog.reception_item_id)
        .all()
    )
    packed_map = {p.reception_item_id: p.p_qty for p in existing_packs}

    qty_to_distribute = body.quantity

    start_dt = None
    if body.start_time:
        try:
            start_dt = datetime.fromisoformat(body.start_time.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass

    end_dt = datetime.utcnow()
    dur_sec = None
    if start_dt:
        dur_sec = (end_dt - start_dt).total_seconds()
        if dur_sec < 0 or dur_sec > 86400:
            dur_sec = 0

    # Distribute
    logs_created = []
    
    total_plan = 0
    total_packed_before = 0

    for rec_item, shipment in items:
        plan = rec_item.quantity
        total_plan += plan
        already_packed = packed_map.get(rec_item.id, 0)
        total_packed_before += already_packed
        
        remaining = max(0, plan - already_packed)
        
        if remaining > 0 and qty_to_distribute > 0:
            pack_now = min(remaining, qty_to_distribute)
            logs_created.append(PackingLog(
                reception_id=shipment.id,
                reception_item_id=rec_item.id,
                barcode=body.barcode,
                quantity=pack_now,
                plan_quantity=plan,
                packed_by=current_user.id,
                box_number=body.box_number,
                tz_text=shipment.name,
                start_time=start_dt,
                end_time=end_dt,
                duration_seconds=dur_sec,
                is_error=0
            ))
            qty_to_distribute -= pack_now
            packed_map[rec_item.id] = already_packed + pack_now

    # If there is leftover packing (overpacking)
    if qty_to_distribute > 0:
        # Dump it on the last item with an error flag
        last_rec_item, last_shipment = items[-1]
        log = PackingLog(
            reception_id=last_shipment.id,
            reception_item_id=last_rec_item.id,
            barcode=body.barcode,
            quantity=qty_to_distribute,
            plan_quantity=last_rec_item.quantity,
            packed_by=current_user.id,
            box_number=body.box_number,
            tz_text=last_shipment.name,
            start_time=start_dt,
            end_time=end_dt,
            duration_seconds=dur_sec,
            is_error=1
        )
        logs_created.append(log)

    for l in logs_created:
        db.add(l)

    db.commit()

    total_packed_now = total_packed_before + body.quantity
    remaining_now = max(0, total_plan - total_packed_now)

    return {
        "status": "ok",
        "progress": f"Осталось по всем ТЗ: {remaining_now}",
        "total_packed": total_packed_now,
        "total_plan": total_plan,
        "is_error": total_packed_now > total_plan
    }

@router.get("")
def list_receptions(
    status_filter: str = "active",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List receptions."""
    statuses = [s.strip() for s in status_filter.split(",")]
    receptions = (
        db.query(Shipment)
        .filter(Shipment.status.in_(statuses), Shipment.type == "reception")
        .order_by(Shipment.created_at.desc())
        .all()
    )
    result = []
    for r in receptions:
        total_scanned = db.query(func.sum(ReceptionItem.quantity)).filter(
            ReceptionItem.shipment_id == r.id
        ).scalar() or 0
        unique_barcodes = db.query(func.count(ReceptionItem.id)).filter(
            ReceptionItem.shipment_id == r.id
        ).scalar() or 0
        result.append({
            "id": r.id,
            "name": r.name,
            "status": r.status,
            "total_scanned": total_scanned,
            "unique_barcodes": unique_barcodes,
            "created_at": r.created_at.strftime("%d.%m.%Y %H:%M") if r.created_at else None,
        })
    return result


@router.get("/{reception_id}")
def get_reception(
    reception_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get reception detail with packing progress."""
    rec = db.query(Shipment).filter(
        Shipment.id == reception_id, Shipment.type == "reception"
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Приёмка не найдена")

    items = (
        db.query(ReceptionItem)
        .filter(ReceptionItem.shipment_id == reception_id)
        .all()
    )

    packing_aggs = (
        db.query(
            PackingLog.reception_item_id,
            func.sum(PackingLog.quantity).label("packed_qty")
        )
        .filter(PackingLog.reception_id == reception_id)
        .group_by(PackingLog.reception_item_id)
        .all()
    )
    packed_map = {p.reception_item_id: p.packed_qty for p in packing_aggs}

    total_plan = sum(i.quantity for i in items)
    total_packed = sum(packed_map.values())

    result_items = []
    for i in items:
        packed = packed_map.get(i.id, 0)
        result_items.append({
            "id": i.id,
            "barcode": i.barcode,
            "quantity": i.quantity,
            "packed": packed,
            "remaining": i.quantity - packed,
            "article": i.article or "—",
            "size": i.size or "—",
        })

    return {
        "id": rec.id,
        "name": rec.name,
        "status": rec.status,
        "total_plan": total_plan,
        "total_packed": total_packed,
        "items": result_items,
    }


@router.post("")
def create_reception(
    body: CreateReceptionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new reception."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Укажите название приёмки")

    rec = Shipment(
        name=name,
        type="reception",
        status="active",
        created_by=current_user.id,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return {"status": "ok", "id": rec.id, "name": name}


@router.post("/upload")
def upload_reception(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create reception from Excel: parse → Shipment(reception) + ReceptionItems + Stock."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    import openpyxl

    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Нужен файл формата .xlsx")

    data = file.file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        ws = wb.active
        items = []
        for row in ws.iter_rows(min_row=1, values_only=True):
            if len(row) < 2:
                continue
            barcode_val, qty_val = row[0], row[1]
            if barcode_val is None or qty_val is None:
                continue
            barcode = str(int(barcode_val)) if isinstance(barcode_val, float) else str(barcode_val)
            barcode = barcode.strip()
            try:
                qty = int(qty_val)
            except (ValueError, TypeError):
                continue
            article_val = str(row[2]).strip() if len(row) > 2 and row[2] is not None else None
            size_val = str(row[3]).strip() if len(row) > 3 and row[3] is not None else None
            if qty > 0 and barcode:
                items.append((barcode, qty, article_val, size_val))
        wb.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка чтения Excel: {e}")

    if not items:
        raise HTTPException(status_code=400, detail="В файле не найдено ни одного товара")

    # Group duplicates
    grouped = {}
    for barcode, qty, article_val, size_val in items:
        if barcode in grouped:
            grouped[barcode] = (grouped[barcode][0] + qty, grouped[barcode][1], grouped[barcode][2])
        else:
            grouped[barcode] = (qty, article_val, size_val)
    items = [(bc, info[0], info[1], info[2]) for bc, info in grouped.items()]

    reception_name = os.path.splitext(file.filename)[0]

    rec = Shipment(
        name=reception_name,
        type="reception",
        status="archived",
        created_by=current_user.id,
    )
    db.add(rec)
    db.flush()
    rec_id = rec.id

    for barcode, qty, article, size in items:
        db.add(ReceptionItem(
            shipment_id=rec_id,
            barcode=barcode,
            quantity=qty,
            article=article,
            size=size,
        ))
        # Update Stock
        stock = db.query(Stock).filter(
            Stock.supplier_name == reception_name,
            Stock.barcode == barcode,
            Stock.is_archived == 0,
        ).first()
        if stock:
            stock.quantity += qty
        else:
            db.add(Stock(
                supplier_name=reception_name,
                barcode=barcode,
                article=article,
                size=size,
                quantity=qty,
            ))
        # Movement
        db.add(StockMovement(
            shipment_id=rec_id,
            movement_type="reception",
            supplier_name=reception_name,
            barcode=barcode,
            article=article,
            size=size,
            quantity=qty,
        ))

    db.commit()
    total_items = sum(q for _, q, _, _ in items)
    return {
        "status": "ok",
        "id": rec_id,
        "name": reception_name,
        "articles": len(items),
        "total": total_items,
    }


@router.post("/{reception_id}/scan")
def scan_reception(
    reception_id: int,
    body: ReceptionScanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Scan barcode into reception (upsert)."""
    barcode = body.barcode.strip()
    scan_qty = max(1, body.quantity)

    rec = db.query(Shipment).filter(
        Shipment.id == reception_id, Shipment.type == "reception"
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Приёмка не найдена")

    existing = db.query(ReceptionItem).filter(
        ReceptionItem.shipment_id == reception_id,
        ReceptionItem.barcode == barcode,
    ).first()

    if existing:
        existing.quantity += scan_qty
        existing.scanned_at = datetime.utcnow()
        qty = existing.quantity
    else:
        item = ReceptionItem(shipment_id=reception_id, barcode=barcode, quantity=scan_qty)
        db.add(item)
        qty = scan_qty

    db.commit()
    return {"status": "ok", "barcode": barcode, "quantity": qty}


@router.post("/{reception_id}/complete")
def complete_reception(
    reception_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Complete reception → add to Stock + archive."""
    rec = db.query(Shipment).filter(
        Shipment.id == reception_id, Shipment.type == "reception"
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Приёмка не найдена")

    if rec.status == "archived":
        raise HTTPException(status_code=400, detail="Приёмка уже завершена")

    rec.status = "archived"
    name = rec.name

    for ri in rec.reception_items:
        stock = db.query(Stock).filter(
            Stock.supplier_name == name,
            Stock.barcode == ri.barcode,
        ).first()
        if stock:
            stock.quantity += ri.quantity
        else:
            db.add(Stock(
                supplier_name=name,
                barcode=ri.barcode,
                article=ri.article,
                size=ri.size,
                quantity=ri.quantity,
            ))
        db.add(StockMovement(
            shipment_id=reception_id,
            movement_type="reception",
            supplier_name=name,
            barcode=ri.barcode,
            article=ri.article,
            size=ri.size,
            quantity=ri.quantity,
        ))

    db.commit()
    return {"status": "ok", "message": f"Приёмка #{reception_id} завершена, остатки обновлены"}


@router.get("/{reception_id}/export-report")
def export_reception_report(
    reception_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export reception report via unified Excel generator."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    rec = db.query(Shipment).filter(
        Shipment.id == reception_id, Shipment.type == "reception"
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Приёмка не найдена")

    try:
        temp_path = generate_reception_report(db, reception_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации отчета: {str(e)}")

    filename = f"#{rec.id} — {rec.name}.xlsx"
    encoded_filename = urllib_quote(filename)

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        "Access-Control-Expose-Headers": "Content-Disposition",
    }

    gc.collect()

    return FileResponse(
        temp_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
        background=BackgroundTask(os.remove, temp_path),
    )


@router.delete("/{reception_id}")
def delete_reception(
    reception_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete reception. Admin and Manager."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    rec = db.query(Shipment).filter(
        Shipment.id == reception_id, Shipment.type == "reception"
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Приёмка не найдена")

    db.delete(rec)
    db.commit()
    return {"status": "ok", "message": f"Приёмка #{reception_id} удалена"}

@router.post("/{reception_id}/pack")
def pack_reception_item(
    reception_id: int,
    body: PackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pack item with KPI tracking for Receptions."""
    barcode = body.barcode.strip()
    quantity = max(1, body.quantity)

    item = db.query(ReceptionItem).filter(
        ReceptionItem.shipment_id == reception_id,
        ReceptionItem.barcode == barcode,
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail=f"Артикул {barcode} не найден в плане приёмки")

    packed_count = (
        db.query(func.sum(PackingLog.quantity))
        .filter(PackingLog.reception_id == reception_id, PackingLog.barcode == barcode)
        .scalar()
    ) or 0

    is_error = 0
    if packed_count + quantity > item.quantity:
        is_error = 1

    start_time = None
    if body.start_time:
        try:
            start_time = datetime.fromisoformat(body.start_time.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            start_time = None

    end_time = datetime.utcnow()
    duration_seconds = None
    if start_time:
        duration_seconds = (end_time - start_time).total_seconds()
        if duration_seconds < 0:
            duration_seconds = 0

    packing_log = PackingLog(
        reception_id=reception_id,
        reception_item_id=item.id,
        barcode=barcode,
        quantity=quantity,
        plan_quantity=item.quantity,
        is_error=is_error,
        packed_by=current_user.id,
        box_number=body.box_number,
        start_time=start_time,
        end_time=end_time,
        duration_seconds=duration_seconds,
    )
    db.add(packing_log)
    db.commit()

    new_packed = packed_count + quantity
    remaining = item.quantity - new_packed

    total_plan = db.query(func.sum(ReceptionItem.quantity)).filter(ReceptionItem.shipment_id == reception_id).scalar() or 0
    total_packed = db.query(func.sum(PackingLog.quantity)).filter(PackingLog.reception_id == reception_id).scalar() or 0

    return {
        "status": "ok",
        "remaining": max(remaining, 0),
        "is_error": is_error,
        "progress": f"{new_packed} из {item.quantity}",
        "total_progress": f"{total_packed} из {total_plan}",
        "total_packed": total_packed,
        "total_plan": total_plan,
    }


@router.get("/{reception_id}/export-packing-report")
def export_packing_report(
    reception_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export packing report for reception via Excel generator."""
    if current_user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    rec = db.query(Shipment).filter(
        Shipment.id == reception_id, Shipment.type == "reception"
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Приёмка не найдена")

    try:
        temp_path = generate_packing_report(db, reception_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации отчёта: {e}")

    filename = f"Упаковка_Приемка_{reception_id}_{rec.name}.xlsx"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{urllib_quote(filename)}",
        "Access-Control-Expose-Headers": "Content-Disposition"
    }

    return FileResponse(
        temp_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
        background=BackgroundTask(os.remove, temp_path),
    )
