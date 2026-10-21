"""FastAPI application composition, lifecycle, middleware, and static pages."""

import os
import sys
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import security
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
from .startup import FALLBACK_DELAY, deferred_tasks
from .routers import admin, books, inventory, reports, sales, sync
from .routers.admin import gdpr_cleanup, gdpr_info
from .routers.books import ocr_scan
from .routers.inventory import book_stats
from .routers.sync import (
    delete_active_basket, get_live_baskets, ping, update_active_basket,
)

app = FastAPI(title="Librairie")

SLOW_REQUEST_S = 0.1


def _warm_ocr():
    """Échauffe le moteur OCR (imports numpy/PIL/onnxruntime coûteux) hors du chemin critique."""
    from . import ocr

    threading.Thread(target=ocr.get_ocr_engine, daemon=True).start()


@app.on_event("startup")
def _start():
    # Rien de lourd ici : l'interface doit peindre le plus vite possible.
    deferred_tasks.register("purge sauvegardes", cleanup_old_backups)
    deferred_tasks.register("boucle miroir", lambda: threading.Thread(target=_mirror_loop, daemon=True).start())
    deferred_tasks.register("échauffement OCR", _warm_ocr)
    # Repli : sans fenêtre (headless, mobile seul), personne n'appellera /api/ui/ready.
    fallback = threading.Timer(FALLBACK_DELAY, deferred_tasks.start)
    fallback.daemon = True
    fallback.start()


@app.middleware("http")
async def mark_dirty(request: Request, call_next):
    resp = await call_next(request)
    if request.method != "GET" and resp.status_code < 400:
        _dirty.set()
    return resp


@app.middleware("http")
async def slow_request_log(request: Request, call_next):
    t0 = time.perf_counter()
    resp = await call_next(request)
    elapsed = time.perf_counter() - t0
    if elapsed > SLOW_REQUEST_S:
        print(
            f"[perf] {request.method} {request.url.path} {elapsed * 1000:.0f} ms",
            file=sys.stderr,
        )
    return resp


@app.post("/api/ui/ready")
def ui_ready(request: Request):
    """Signal du premier rendu de l'interface : lance les tâches différées."""
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Réservé au poste de caisse")
    deferred_tasks.start()
    return {"ok": deferred_tasks.started}


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
