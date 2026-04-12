# -*- coding: utf-8 -*-
"""Database initialisation & admin seed.

Handles:
1. Fresh DB — creates all tables + admin user.
2. Existing DB — adds missing columns/tables via ALTER TABLE.
"""

import logging
from sqlalchemy import inspect, text

from app.database import engine, SessionLocal, Base
from app.models import User  # noqa – registers model with Base
from app.auth import hash_password
from app.config import ADMIN_USERNAME, ADMIN_PASSWORD

log = logging.getLogger("alto.seed")


def _column_exists(inspector, table: str, column: str) -> bool:
    cols = [c["name"] for c in inspector.get_columns(table)]
    return column in cols


def _table_exists(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def _migrate_add_column(conn, table: str, column: str, col_type: str, default=None):
    """Safely add a column to an existing table."""
    default_clause = f" DEFAULT {default}" if default is not None else ""
    sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}"
    conn.execute(text(sql))
    log.info(f"Migrated: {table}.{column} ({col_type})")


def init_db():
    """Create tables (if missing), run migrations, seed admin."""
    inspector = inspect(engine)

    # --- Migrate existing users table if needed ---
    if _table_exists(inspector, "users"):
        with engine.connect() as conn:
            if not _column_exists(inspector, "users", "password_hash"):
                _migrate_add_column(conn, "users", "password_hash", "TEXT", "''")

            if not _column_exists(inspector, "users", "created_at"):
                _migrate_add_column(conn, "users", "created_at", "DATETIME")

            if not _column_exists(inspector, "users", "full_name"):
                _migrate_add_column(conn, "users", "full_name", "TEXT")

            conn.commit()

    # --- Migrate packed table: add packed_by ---
    if _table_exists(inspector, "packed"):
        with engine.connect() as conn:
            if not _column_exists(inspector, "packed", "packed_by"):
                _migrate_add_column(conn, "packed", "packed_by", "INTEGER")
            conn.commit()

    # --- Migrate packing_logs table: add tz_text ---
    if _table_exists(inspector, "packing_logs"):
        with engine.connect() as conn:
            if not _column_exists(inspector, "packing_logs", "tz_text"):
                _migrate_add_column(conn, "packing_logs", "tz_text", "TEXT")
            conn.commit()

    # --- Create any remaining tables (including packing_logs, supply_logs) ---
    Base.metadata.create_all(bind=engine)

    # --- Seed admin user ---
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == ADMIN_USERNAME).first()
        if admin is None:
            admin = User(
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                role="admin",
                full_name="Администратор",
            )
            db.add(admin)
            db.commit()
            log.info(f"Admin user '{ADMIN_USERNAME}' created.")
        else:
            # Ensure admin has a password hash (migration from bot DB)
            if not admin.password_hash:
                admin.password_hash = hash_password(ADMIN_PASSWORD)
                admin.role = "admin"
                db.commit()
                log.info(f"Admin user '{ADMIN_USERNAME}' password hash set.")
    finally:
        db.close()
