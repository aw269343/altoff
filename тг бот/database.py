#!/opt/python/python-3.10.1/bin/python
# -*- coding: utf-8 -*-
# database.py — Модели БД для системы фулфилмента "Alto" v2
# CGI-режим: SQLite, абсолютные пути.
#
# Таблицы:
#   Users          — пользователи (username, role: admin/manager/storekeeper)
#   Shipments      — поставки/приёмки (name, type, status, last_box_number)
#   Items          — план поставки: штрихкод + кол-во
#   Packed         — факт поставки: штрихкод товара + номер короба
#   ReceptionItems — факт приёмки: штрихкод + кол-во (без плана)
#   Stock          — складской учёт: остатки по баркодам/поставщикам
#   StockMovement  — история движений товара

import os
from datetime import datetime
from contextlib import contextmanager

from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# ---------------------------------------------------------------------------
#  Абсолютный путь к БД
# ---------------------------------------------------------------------------
BASE_DIR = "/var/www/u3262373/data/www/altoff.online"
DATABASE_PATH = os.path.join(BASE_DIR, "fulfillment.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ---------------------------------------------------------------------------
#  Модели
# ---------------------------------------------------------------------------

class User(Base):
    """Пользователь системы с ролью."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)   # @username (без @)
    role = Column(String, nullable=False)   # "admin" | "manager" | "storekeeper"
    added_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User @{self.username} [{self.role}]>"


class Shipment(Base):
    """Поставка или приёмка."""
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    type = Column(String, default="shipment")            # shipment | reception
    status = Column(String, default="active")            # active | completed | archived
    last_box_number = Column(Integer, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("Item", back_populates="shipment", cascade="all, delete-orphan")
    packed = relationship("Packed", back_populates="shipment", cascade="all, delete-orphan")
    reception_items = relationship("ReceptionItem", back_populates="shipment", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<Shipment #{self.id} '{self.name}' [{self.type}/{self.status}]>"


class Item(Base):
    """План поставки: штрихкод + ожидаемое количество + доп. поля."""
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=False)
    barcode = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    article = Column(String, nullable=True)       # Артикул производителя (необязательный)
    size = Column(String, nullable=True)           # Размер (необязательный)

    shipment = relationship("Shipment", back_populates="items")

    def __repr__(self):
        return f"<Item {self.barcode} x{self.quantity}>"


class Packed(Base):
    """Факт упаковки: какой товар в каком коробе."""
    __tablename__ = "packed"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    barcode = Column(String, nullable=False)           # ШК товара
    box_number = Column(Integer, nullable=False)       # Номер короба (1, 2, 3...)
    scanned_at = Column(DateTime, default=datetime.utcnow)

    shipment = relationship("Shipment", back_populates="packed")
    item = relationship("Item")

    def __repr__(self):
        return f"<Packed {self.barcode} -> box #{self.box_number}>"


class ReceptionItem(Base):
    """Факт приёмки: штрихкод + кол-во (без плана)."""
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
    """Складской учёт: остатки товара."""
    __tablename__ = "stock"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_name = Column(String, nullable=False, index=True)  # Название поставщика (= имя приёмки)
    barcode = Column(String, nullable=False, index=True)
    article = Column(String, nullable=True)
    size = Column(String, nullable=True)
    quantity = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_archived = Column(Integer, default=0)  # 0 = активный, 1 = архивный

    def __repr__(self):
        return f"<Stock {self.barcode} x{self.quantity} [{self.supplier_name}]>"


class StockMovement(Base):
    """История движений товара (приёмка / отгрузка)."""
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=True)
    movement_type = Column(String, nullable=False)  # "reception" | "shipment"
    supplier_name = Column(String, nullable=False)
    barcode = Column(String, nullable=False)
    article = Column(String, nullable=True)
    size = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)      # +N для приёмки, -N для отгрузки
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<StockMovement {self.movement_type} {self.barcode} qty={self.quantity}>"



# ---------------------------------------------------------------------------
#  Утилиты
# ---------------------------------------------------------------------------

def init_db():
    """Создать все таблицы (если не существуют)."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session():
    """Контекстный менеджер для работы с сессией."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
