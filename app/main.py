"""
app/main.py
-------------------------------------------------------------------------------
Point d'entrée principal de l'application FastAPI.
Structure modulaire allégée avec inclusion des routeurs spécialisés :
- app/routers/books.py      : Catalogue, livres, lots, packs et scans
- app/routers/sales.py      : Encaissements, trésorerie, règlements, réservations, stats
- app/routers/receptions.py : Réceptions de stock, lots et ajustements
- app/routers/ocr.py        : Traitement optique d'images
- app/routers/sync.py       : Flux SSE temps réel, régie CCTV, appairage mobile
- app/routers/reports.py    : Import/Export Excel et gestion des sauvegardes
- app/routers/options.py    : Utilisateurs, journal d'audit, options, propriétaires
-------------------------------------------------------------------------------
"""

import asyncio
import json
import os
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, excel_io, security, ocr
from .routers import books, sales, receptions, ocr as ocr_router, sync, reports, options

app = FastAPI(title="Librairie")
db.init()


class LiveHub:
    """Hub temps réel (SSE) & registre en mémoire des paniers actifs."""
    def __init__(self):
        self.listeners = set()  # set of (loop, asyncio.Queue)
        self.lock = threading.Lock()
        self.active_baskets = {}  # device_id -> dict

    def register(self, loop, queue):
        with self.lock:
            self.listeners.add((loop, queue))

    def unregister(self, loop, queue):
        with self.lock:
            self.listeners.discard((loop, queue))

    def broadcast(self, event_type: str, data: dict):
        payload = json.dumps({"type": event_type, "data": data, "timestamp": time.time()})
        with self.lock:
            dead = []
            for loop, q in list(self.listeners):
                try:
                    loop.call_soon_threadsafe(q.put_nowait, payload)
                except Exception:
                    dead.append((loop, q))
            for d in dead:
                self.listeners.discard(d)

    def update_basket(self, device_id: str, basket_data: dict, action: dict = None):
        now = time.time()
        basket_data["updated_at"] = now
        if basket_data.get("qty", 0) > 0 or basket_data.get("items"):
            basket_data["status"] = "scanning"
        else:
            basket_data["status"] = "connected"

        with self.lock:
            self.active_baskets[device_id] = basket_data
            self._cleanup_expired()
            active_list = self._prepare_baskets()

        self.broadcast("baskets_updated", {
            "baskets": active_list,
            "action": action,
            "device_id": device_id,
            "user_name": basket_data.get("user_name")
        })

    def remove_basket(self, device_id: str, action: dict = None):
        with self.lock:
            act_type = (action or {}).get("type", "")
            if act_type in ("session_closed", "disconnected", "unpaired"):
                removed = self.active_baskets.pop(device_id, None)
            else:
                if device_id in self.active_baskets:
                    self.active_baskets[device_id]["qty"] = 0
                    self.active_baskets[device_id]["total"] = 0.0
                    self.active_baskets[device_id]["items"] = []
                    self.active_baskets[device_id]["status"] = "connected"
                    self.active_baskets[device_id]["updated_at"] = time.time()
                    removed = self.active_baskets[device_id]
                else:
                    removed = None
            self._cleanup_expired()
            active_list = self._prepare_baskets()

        if removed:
            self.broadcast("baskets_updated", {
                "baskets": active_list,
                "action": action or {"type": "cart_cleared"},
                "device_id": device_id,
                "user_name": removed.get("user_name")
            })

    def get_active_baskets(self):
        with self.lock:
            self._cleanup_expired()
            return self._prepare_baskets()

    def _prepare_baskets(self):
        now = time.time()
        res = []
        for v in self.active_baskets.values():
            item = dict(v)
            age = now - item.get("updated_at", now)
            item["idle_sec"] = int(age)
            item["state"] = "idle" if age > 45 else "active"
            res.append(item)
        return res

    def _cleanup_expired(self):
        cutoff = time.time() - 150
        expired = [k for k, v in self.active_baskets.items() if v.get("updated_at", 0) < cutoff]
        for k in expired:
            del self.active_baskets[k]


live_hub = LiveHub()

STATIC = os.path.join(sys._MEIPASS, "app", "static") if getattr(sys, "frozen", False) \
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MIRROR = os.path.join(db.DATA_DIR, "Bibliotheque_miroir.xlsx")
BACKUPS = os.path.join(db.DATA_DIR, "sauvegardes")
os.makedirs(BACKUPS, exist_ok=True)
_dirty = threading.Event()


def cleanup_old_backups(max_hourly: int = 24, max_daily: int = 30, max_pre_ops: int = 10) -> int:
    return reports.cleanup_old_backups(max_hourly=max_hourly, max_daily=max_daily, max_pre_ops=max_pre_ops)


def _mirror_loop():
    """Excel toujours à jour en arrière-plan + snapshots SQLite et Excel ultra-sécurisés via .tmp et renommage atomique."""
    last_day = None
    last_hourly_backup = 0
    while True:
        time.sleep(4)
        now = datetime.now()
        today = now.date().isoformat()
        is_dirty = _dirty.is_set()
        
        if is_dirty or last_day != today:
            _dirty.clear()
            try:
                excel_io.export_workbook(MIRROR)
                
                daily_db = os.path.join(BACKUPS, f"librairie_{today}.db")
                db.safe_backup_db(daily_db)
                
                daily_xl = os.path.join(BACKUPS, f"Bibliotheque_{today}.xlsx")
                tmp_xl = daily_xl + ".tmp"
                shutil.copyfile(MIRROR, tmp_xl)
                os.replace(tmp_xl, daily_xl)
                
                if time.time() - last_hourly_backup > 3600 or last_day != today:
                    stamp = now.strftime("%Y%m%d_%H%M")
                    db.safe_backup_db(os.path.join(BACKUPS, f"librairie_{stamp}.db"))
                    last_hourly_backup = time.time()
                    cleanup_old_backups()

                if last_day != today:
                    cleanup_old_backups()

                last_day = today
            except Exception as e:
                print("Erreur boucle de sauvegarde résiliente:", e)


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


# Doit rester APRÈS les autres middlewares : le dernier enregistré est le plus externe (premier exécuté).
app.middleware("http")(security.security_gate)


# ---------- Moment de culte / Session maître ----------
MASTER_SESSION_MOMENT: Optional[str] = None

def get_current_moment() -> str:
    if MASTER_SESSION_MOMENT:
        return MASTER_SESSION_MOMENT
    now = datetime.now()
    if now.weekday() == 6:  # Dimanche
        return "2e Culte (Jeunes EJP)" if now.hour >= 12 else "1er Culte (Principal)"
    return "En semaine / Autre"


# ---------- Inclusion des Routeurs Modulaires ----------
app.include_router(books.router)
app.include_router(sales.router)
app.include_router(receptions.router)
app.include_router(ocr_router.router)
app.include_router(sync.router)
app.include_router(reports.router)
app.include_router(options.router)


# ---------- Rétrocompatibilité / Re-exports symboles pour les tests existants ----------
from .routers.books import (
    BookIn, PackItem, _books, _mobile_book, book_stats, scan_book, search_books,
    _dump, get_current_user
)
from .routers.sales import (
    SaleIn, LineIn, AllocIn, PaymentPartIn, CashMovementIn, SettleIn, ResIn,
    sales as get_sales, sale_add, sale_del, treasury_summary, cash_movement_add, cash_movement_del,
    settlements, settle, res_list, res_add, res_upd, res_del,
    gdpr_info, gdpr_cleanup, stats, stats_matrix
)
from .routers.receptions import LotIn, AdjIn, lot_add, lot_adjust
from .routers.ocr import OcrScanIn, ocr_scan
from .routers.sync import (
    PairIn, ActiveBasketIn, ActiveBasketItem, ActivityEventIn,
    update_active_basket, delete_active_basket, post_live_activity,
    get_live_baskets, live_stream, ping, mobile_info, mobile_pairing, mobile_pair
)
from .routers.options import (
    UserIn, OwnerIn, DropdownItemIn, DropdownItemRenameIn,
    get_users, add_user, upd_user, del_user, get_audit, undo_audit,
    get_options, add_option, get_option_impact, rename_or_merge_option, delete_option,
    owners, owner_add, owner_upd, owner_del
)
from .routers.reports import (
    import_xlsx, export_xlsx, backup, list_backups, download_backup,
    delete_backup_file, trigger_backup_cleanup, restore_backup
)


# ---------- Vues HTML Statiques ----------
@app.get("/mobile")
def mobile_view():
    return FileResponse(os.path.join(STATIC, "mobile.html"))


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")

