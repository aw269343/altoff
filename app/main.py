# -*- coding: utf-8 -*-
"""FastAPI application entry point for Alto Fulfillment."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response

from app.config import ALLOWED_ORIGINS
from app.seed import init_db
from app.routers import (
    auth_router,
    users_router,
    shipments_router,
    receptions_router,
    stock_router,
    history_router,
    analytics_router,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("alto")

APP_DIR = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB & seed admin."""
    log.info("Initialising database...")
    init_db()
    log.info("Database ready.")
    yield


app = FastAPI(title="Alto Fulfillment", version="1.0.0", lifespan=lifespan)

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return Response(status_code=204)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length"],
)

# --- Static files ---
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")

# --- Templates ---
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

# --- API routers ---
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(shipments_router.router)
app.include_router(receptions_router.router)
app.include_router(stock_router.router)
app.include_router(history_router.router)
app.include_router(analytics_router.router)


# --- HTML pages ---

@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/login")


@app.get("/index.php")
async def index_php_redirect():
    return RedirectResponse(url="/login")


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard")
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/scanner")
async def scanner_page(request: Request):
    return templates.TemplateResponse("scanner.html", {"request": request})


@app.get("/reception")
async def reception_page(request: Request):
    return templates.TemplateResponse("receipt.html", {"request": request})


@app.get("/shipment")
async def shipment_page(request: Request):
    return templates.TemplateResponse("boxes.html", {"request": request})


@app.get("/stock")
async def stock_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/history")
async def history_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})
