# -*- coding: utf-8 -*-
"""SQLAlchemy models for Alto Fulfillment system.

Tables:
  User           — users with password_hash, role, and full_name
  Shipment       — shipments / receptions
  Item           — shipment plan items (barcode + qty)
  Packed         — packed items (barcode + box number)
  ReceptionItem  — reception scanned items
  Stock          — warehouse stock by supplier/barcode
  StockMovement  — stock movement history
  PackingLog     — packing session log with time-tracking for KPI
  SupplyLog      — warehouseman box processing log for KPI
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """System user with hashed password, RBAC role, and full name."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "admin" | "manager" | "packer" | "warehouseman" | "storekeeper"
    full_name = Column(String, nullable=True)  # ФИО для KPI-таблиц
    created_at = Column(DateTime, default=datetime.utcnow)

    # Legacy field kept for DB migration compatibility
    telegram_id = Column(Integer, unique=True, nullable=True, index=True)

    def __repr__(self):
        return f"<User {self.username} [{self.role}]>"

    @property
    def display_name(self):
        """Return full_name if set, otherwise username."""
        return self.full_name or self.username


class Shipment(Base):
    """Shipment or reception record."""
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    type = Column(String, default="shipment")      # shipment | reception
    status = Column(String, default="active")       # active | completed | archived
    last_box_number = Column(Integer, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("Item", back_populates="shipment", cascade="all, delete-orphan")
    packed = relationship("Packed", back_populates="shipment", cascade="all, delete-orphan")
    reception_items = relationship("ReceptionItem", back_populates="shipment", cascade="all, delete-orphan")
    packing_logs = relationship("PackingLog", back_populates="reception", cascade="all, delete-orphan")
    supply_logs = relationship("SupplyLog", back_populates="shipment", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<Shipment #{self.id} '{self.name}' [{self.type}/{self.status}]>"


class Item(Base):
    """Shipment plan item: barcode + expected quantity."""
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=False)
    barcode = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    article = Column(String, nullable=True)
    size = Column(String, nullable=True)

    shipment = relationship("Shipment", back_populates="items")

    def __repr__(self):
        return f"<Item {self.barcode} x{self.quantity}>"


class Packed(Base):
    """Packed item: which product in which box."""
    __tablename__ = "packed"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    barcode = Column(String, nullable=False)
    box_number = Column(Integer, nullable=False)
    packed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    scanned_at = Column(DateTime, default=datetime.utcnow)

    shipment = relationship("Shipment", back_populates="packed")
    item = relationship("Item")
    packer = relationship("User", foreign_keys=[packed_by])

    def __repr__(self):
        return f"<Packed {self.barcode} -> box #{self.box_number}>"


class ReceptionItem(Base):
    """Reception scanned item: barcode + quantity (no plan)."""
    __tablename__ = "reception_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=False)
    barcode = Column(String, nullable=False)
    quantity = Column(Integer, default=1)
    article = Column(String, nullable=True)
    size = Column(String, nullable=True)
    scanned_at = Column(DateTime, default=datetime.utcnow)

    shipment = relationship("Shipment", back_populates="reception_items")

    def __repr__(self):
        return f"<ReceptionItem {self.barcode} x{self.quantity}>"


class Stock(Base):
    """Warehouse stock: product balance by supplier."""
    __tablename__ = "stock"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_name = Column(String, nullable=False, index=True)
    barcode = Column(String, nullable=False, index=True)
    article = Column(String, nullable=True)
    size = Column(String, nullable=True)
    quantity = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_archived = Column(Integer, default=0)  # 0 = active, 1 = archived

    def __repr__(self):
        return f"<Stock {self.barcode} x{self.quantity} [{self.supplier_name}]>"


class StockMovement(Base):
    """Stock movement history (reception / shipment)."""
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=True)
    movement_type = Column(String, nullable=False)  # "reception" | "shipment"
    supplier_name = Column(String, nullable=False)
    barcode = Column(String, nullable=False)
    article = Column(String, nullable=True)
    size = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)      # +N reception, -N shipment
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<StockMovement {self.movement_type} {self.barcode} qty={self.quantity}>"


class PackingLog(Base):
    """Packing session log — tracks each packing action with timing for KPI.

    KPI formula: speed = SUM(quantity) / SUM(end_time - start_time) in hours
    is_error = 1 when quantity > plan_quantity (overpacking)
    """
    __tablename__ = "packing_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reception_id = Column(Integer, ForeignKey("shipments.id"), nullable=False)
    reception_item_id = Column(Integer, ForeignKey("reception_items.id"), nullable=False)
    barcode = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)            # фактически упаковано
    plan_quantity = Column(Integer, nullable=False)        # план по ТЗ
    is_error = Column(Integer, default=0)                  # 1 = overpacking
    packed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    box_number = Column(Integer, nullable=True)
    tz_text = Column(String, nullable=True)                # название ТЗ (приёмки)
    start_time = Column(DateTime, nullable=True)           # кнопка ОК (старт)
    end_time = Column(DateTime, nullable=True)             # кнопка Упаковать (финиш)
    duration_seconds = Column(Float, nullable=True)        # pre-calculated duration
    created_at = Column(DateTime, default=datetime.utcnow)

    reception = relationship("Shipment", back_populates="packing_logs")
    reception_item = relationship("ReceptionItem")
    packer = relationship("User", foreign_keys=[packed_by])

    def __repr__(self):
        return f"<PackingLog {self.barcode} qty={self.quantity} err={self.is_error}>"


class SupplyLog(Base):
    """Warehouseman box processing log — tracks each box action for KPI.

    KPI formula: speed = COUNT(DISTINCT box_id) / SUM(end_time - start_time) in hours
    """
    __tablename__ = "supply_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=True)
    box_id = Column(String, nullable=False, index=True)    # штрихкод коробки
    action = Column(String, default="processed")           # "received" | "processed" | "shipped"
    processed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shipment = relationship("Shipment", back_populates="supply_logs")
    worker = relationship("User", foreign_keys=[processed_by])

    def __repr__(self):
        return f"<SupplyLog box={self.box_id} action={self.action}>"
