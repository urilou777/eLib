"""FastAPI application composition, lifecycle, middleware, and static pages."""

import os
import sys
import threading

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import ocr, security
from .api_common import dump_model as _dump
from .realtime import LiveHub, live_hub
from .schemas import ActiveBasketIn, ActiveBasketItem, AllocIn, BookIn, ResIn
from .services import (
    BACKUPS,
    MIRROR,
    _dirty,
    _mirror_loop,
    _mobile_book,
    cleanup_old_backups,
)
from .routers import admin, books, inventory, reports, sales, sync
from .routers.admin import gdpr_cleanup, gdpr_info
from .routers.books import ocr_scan
from .routers.inventory import book_stats
from .routers.sync import (
    delete_active_basket, get_live_baskets, ping, update_active_basket,
)

app = FastAPI(title="Librairie")

@app.on_event("startup")
def _start():
    cleanup_old_backups()
    threading.Thread(target=_mirror_loop, daemon=True).start()
    threading.Thread(target=ocr.get_ocr_engine, daemon=True).start()


@app.middleware("http")
async def mark_dirty(request: Request, call_next):
    resp = await call_next(request)
    if request.method != "GET" and resp.status_code < 400:
        _dirty.set()
    return resp


@app.exception_handler(ValueError)
async def _ve(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


# Register after the other middleware so the security gate remains outermost.
app.middleware("http")(security.security_gate)

app.include_router(inventory.router)
app.include_router(books.router)
app.include_router(sales.router)
app.include_router(admin.router)
app.include_router(reports.router)
app.include_router(sync.router)

STATIC = os.path.join(sys._MEIPASS, "app", "static") if getattr(sys, "frozen", False) \
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.get("/mobile")
def mobile_view():
    return FileResponse(os.path.join(STATIC, "mobile.html"))


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
