"""
app/routers/sync.py
-------------------------------------------------------------------------------
Routeur FastAPI dédié aux opérations réseau, temps réel (SSE live streams),
appairage mobile, sessions maîtres et certificats HTTPS locaux.
-------------------------------------------------------------------------------
"""

import asyncio
import io
import json
import socket
import time
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from .. import db, security

try:
    from .. import certs
except ImportError:
    certs = None

router = APIRouter(prefix="/api", tags=["sync"])


def _dump(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model)


def get_current_user(request: Request) -> str:
    import re
    from urllib.parse import unquote
    raw = request.headers.get("X-User") or request.query_params.get("user") or ""
    u = re.sub(r"[\x00-\x1f\x7f<>]", "", unquote(raw)).strip()[:60]
    return u or "Anonyme"


def _mobile_base():
    port, ips = security.state["https_port"], security.local_ips()
    return f"https://{ips[0]}:{port}" if (port and ips and certs) else None


def _get_live_hub():
    from ..main import live_hub
    return live_hub


def _get_current_moment() -> str:
    from ..main import get_current_moment
    return get_current_moment()


# ---------- Modèles Pydantic ----------
class PairIn(BaseModel):
    code: str = Field(min_length=8, max_length=64)
    name: Optional[str] = Field(None, max_length=60)


class ActiveBasketItem(BaseModel):
    title: str
    qty: int = 1
    price: float = 0.0


class ActiveBasketIn(BaseModel):
    user_name: Optional[str] = "Libraire"
    total: float = 0.0
    qty: int = 0
    items: List[ActiveBasketItem] = Field(default_factory=list)
    mode: Optional[str] = "sale"
    moment: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    star: Optional[int] = 0
    battery: Optional[float] = None
    is_charging: Optional[bool] = None
    action: Optional[dict] = None


class ActivityEventIn(BaseModel):
    type: str
    user_name: Optional[str] = "Libraire"
    title: Optional[str] = None
    detail: Optional[str] = None
    data: Optional[dict] = None


# ---------- Moment de Session Maître ----------
@router.get("/session/moment")
def get_session_moment():
    from .. import main
    return {"moment": main.MASTER_SESSION_MOMENT, "effective_moment": main.get_current_moment()}


@router.post("/session/moment")
def set_session_moment(body: dict):
    from .. import main
    m = body.get("moment")
    main.MASTER_SESSION_MOMENT = m.strip() if (m and isinstance(m, str) and m.strip()) else None
    return {"ok": True, "moment": main.MASTER_SESSION_MOMENT, "effective_moment": main.get_current_moment()}


# ---------- Ping & Santé Réseau ----------
@router.get("/ping")
def ping():
    return {
        "ok": True,
        "time": time.time(),
        "host": socket.gethostname(),
        "mdns_host": f"{socket.gethostname().lower()}.local",
        "ips": security.local_ips(),
        "active_moment": _get_current_moment()
    }


# ---------- Mobile & Appairage ----------
@router.get("/mobile/info")
def mobile_info():
    base = _mobile_base()
    hname = socket.gethostname().lower()
    return {"enabled": bool(base), "base_url": base, "ips": security.local_ips(),
            "mdns_host": f"{hname}.local",
            "ca_fingerprint": certs.ca_fingerprint() if base else None,
            "devices": security.list_devices()}


@router.post("/mobile/pairing")
def mobile_pairing():
    base = _mobile_base()
    if not base:
        raise HTTPException(503, "Le mode mobile (HTTPS) n'est pas actif sur ce poste. Lancez Installer_Mobile.bat.")
    code = security.new_pairing_code()
    return {"url": f"{base}/mobile#pair={code}", "expires_in": security.PAIRING_TTL}


@router.post("/mobile/pair")
def mobile_pair(body: PairIn, request: Request):
    ip = request.client.host if request.client else "?"
    token = security.redeem_pairing(body.code, body.name, ip)
    if not token:
        raise HTTPException(401, "Code d'appairage invalide ou expiré : affichez un nouveau QR code sur le poste")
    with db.tx() as c:
        db.log_audit(c, "Système", "INSERT", "device", None, f"Téléphone appairé « {(body.name or 'Téléphone')[:60]} » ({ip})")
    return {"token": token}


@router.get("/mobile/me")
def mobile_me(request: Request):
    return {"device": request.state.device["name"]}


@router.delete("/mobile/devices/{did}")
def mobile_revoke(did: int, request: Request):
    security.revoke_device(did)
    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "DELETE", "device", did, f"Appairage téléphone #{did} révoqué")
    return {"ok": True}


# ---------- Panier Actif Temps Réel & CCTV ----------
@router.post("/mobile/active-cart")
def update_active_basket(b: ActiveBasketIn, request: Request):
    dev = security.device_from_request(request)
    dev_id = str(dev["id"]) if dev else (request.client.host if request.client else "local")
    dev_name = dev["name"] if dev else (b.user_name or "Mobile")
    data = {
        "device_id": dev_id,
        "device_name": dev_name,
        "user_name": b.user_name or dev_name,
        "total": round(b.total, 2),
        "qty": b.qty,
        "items": [getattr(i, 'model_dump', i.dict)() for i in b.items[:15]],
        "mode": b.mode or "sale",
        "moment": b.moment,
        "gender": b.gender,
        "age": b.age,
        "star": b.star or 0,
        "battery": b.battery,
        "is_charging": b.is_charging
    }
    _get_live_hub().update_basket(dev_id, data, action=b.action)
    return {"ok": True}


@router.delete("/mobile/active-cart")
def delete_active_basket(request: Request, reason: Optional[str] = "cart_cleared"):
    dev = security.device_from_request(request)
    dev_id = str(dev["id"]) if dev else (request.client.host if request.client else "local")
    dev_name = dev["name"] if dev else "Mobile"
    _get_live_hub().remove_basket(dev_id, action={"type": reason, "user_name": dev_name})
    return {"ok": True}


@router.post("/live/activity")
def post_live_activity(ev: ActivityEventIn, request: Request):
    dev = security.device_from_request(request)
    dev_name = dev["name"] if dev else (ev.user_name or "Poste")
    _get_live_hub().broadcast("activity_logged", {
        "type": ev.type,
        "user_name": ev.user_name or dev_name,
        "title": ev.title,
        "detail": ev.detail,
        "data": ev.data or {}
    })
    return {"ok": True}


@router.get("/live/baskets")
def get_live_baskets():
    return {"baskets": _get_live_hub().get_active_baskets()}


@router.get("/live/stream")
async def live_stream(request: Request):
    loop = asyncio.get_event_loop()
    q = asyncio.Queue(maxsize=200)
    live = _get_live_hub()
    live.register(loop, q)

    async def event_generator():
        try:
            init_msg = json.dumps({
                "type": "init",
                "data": {"baskets": live.get_active_baskets()},
                "timestamp": time.time()
            })
            yield f"data: {init_msg}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield f": ping\n\n"
        finally:
            live.unregister(loop, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/ca.crt")
def download_ca():
    if not certs:
        raise HTTPException(503, "HTTPS local non disponible")
    return Response(certs.ca_pem(), media_type="application/x-x509-ca-cert",
                    headers={"Content-Disposition": 'attachment; filename="Librairie-CA.crt"'})


@router.get("/qr")
def qr_svg(data: str):
    if not data.startswith("https://") or len(data) > 300:
        raise HTTPException(400, "Donnée invalide")
    import segno
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=8, border=2, dark="#000000", light="#ffffff")
    return Response(buf.getvalue(), media_type="image/svg+xml")
