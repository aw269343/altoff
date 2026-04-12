# -*- coding: utf-8 -*-
"""Конфигурация приложения Alto Fulfillment."""

import os
import secrets
from dotenv import load_dotenv

# Загружаем переменные из .env файла (если он есть)
load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Database ---
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////var/www/alto_wms/fulfillment.db")

# --- JWT ---
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_urlsafe(64))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

# --- Admin seed ---
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "tem4o")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Artem89687431555")

# --- CORS ---
_origins = os.environ.get("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [origin.strip() for origin in _origins.split(",")] if _origins else ["*"]
