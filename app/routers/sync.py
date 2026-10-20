"""Sync API routes."""

from fastapi import APIRouter
import asyncio
import io
import json
import time
import socket
from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from typing import Optional
from .. import certs, db, security
from ..api_common import get_current_user
from ..realtime import live_hub
from ..schemas import ActiveBasketIn, ActivityEventIn, PairIn
from ..services import (
    _mobile_base,
    get_current_moment,
    get_master_session_moment,
    set_master_session_moment,
)

router = APIRouter()

@router.get("/api/session/moment")
def get_session_moment():
    return {
        "moment": get_master_session_moment(),
        "effective_moment": get_current_moment(),
    }

@router.post("/api/session/moment")
def set_session_moment(body: dict):
    m = body.get("moment")
    moment = m.strip() if (m and isinstance(m, str) and m.strip()) else None
    set_master_session_moment(moment)
    return {
        "ok": True,
        "moment": moment,
        "effective_moment": get_current_moment(),
    }

@router.get("/api/ping")
def ping():
    return {
        "ok": True,
        "time": time.time(),
        "host": socket.gethostname(),
        "mdns_host": f"{socket.gethostname().lower()}.local",
        "ips": security.local_ips(),
        "active_moment": get_current_moment()
    }

@router.get("/api/mobile/info")
def mobile_info():
    base = _mobile_base()
    hname = socket.gethostname().lower()
    return {"enabled": bool(base), "base_url": base, "ips": security.local_ips(),
            "mdns_host": f"{hname}.local",
            "ca_fingerprint": certs.ca_fingerprint() if base else None,
            "devices": security.list_devices()}

@router.post("/api/mobile/pairing")
def mobile_pairing():
    base = _mobile_base()
    if not base:
        raise HTTPException(503, "Le mode mobile (HTTPS) n'est pas actif sur ce poste. Lancez Installer_Mobile.bat.")
    code = security.new_pairing_code()
    # Le code est dans le FRAGMENT (#) : il n'est jamais envoyé au serveur ni consigné dans les journaux/Referer
    return {"url": f"{base}/mobile#pair={code}", "expires_in": security.PAIRING_TTL}

@router.post("/api/mobile/pair")
def mobile_pair(body: PairIn, request: Request):
    ip = request.client.host if request.client else "?"
    token = security.redeem_pairing(body.code, body.name, ip)
    if not token:
        raise HTTPException(401, "Code d'appairage invalide ou expiré : affichez un nouveau QR code sur le poste")
    with db.tx() as c:
        db.log_audit(c, "Système", "INSERT", "device", None, f"Téléphone appairé « {(body.name or 'Téléphone')[:60]} » ({ip})")
    return {"token": token}

@router.get("/api/mobile/me")
def mobile_me(request: Request):
    return {"device": request.state.device["name"]}

@router.delete("/api/mobile/devices/{did}")
def mobile_revoke(did: int, request: Request):
    security.revoke_device(did)
    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "DELETE", "device", did, f"Appairage téléphone #{did} révoqué")
    return {"ok": True}

@router.post("/api/mobile/active-cart")
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
    live_hub.update_basket(dev_id, data, action=b.action)
    return {"ok": True}

@router.delete("/api/mobile/active-cart")
def delete_active_basket(request: Request, reason: Optional[str] = "cart_cleared"):
    dev = security.device_from_request(request)
    dev_id = str(dev["id"]) if dev else (request.client.host if request.client else "local")
    dev_name = dev["name"] if dev else "Mobile"
    live_hub.remove_basket(dev_id, action={"type": reason, "user_name": dev_name})
    return {"ok": True}

@router.post("/api/live/activity")
def post_live_activity(ev: ActivityEventIn, request: Request):
    dev = security.device_from_request(request)
    dev_name = dev["name"] if dev else (ev.user_name or "Poste")
    live_hub.broadcast("activity_logged", {
        "type": ev.type,
        "user_name": ev.user_name or dev_name,
        "title": ev.title,
        "detail": ev.detail,
        "data": ev.data or {}
    })
    return {"ok": True}

@router.get("/api/live/baskets")
def get_live_baskets():
    return {"baskets": live_hub.get_active_baskets()}

@router.get("/api/live/stream")
async def live_stream(request: Request):
    loop = asyncio.get_event_loop()
    q = asyncio.Queue(maxsize=200)
    live_hub.register(loop, q)

    async def event_generator():
        try:
            # Envoi initial de l'état actuel des paniers actifs
            init_msg = json.dumps({
                "type": "init",
                "data": {"baskets": live_hub.get_active_baskets()},
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
            live_hub.unregister(loop, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/api/ca.crt")
def download_ca():
    """Certificat PUBLIC de la CA locale (jamais de clé privée) à installer sur les téléphones."""
    if not certs:
        raise HTTPException(503, "HTTPS local non disponible")
    return Response(certs.ca_pem(), media_type="application/x-x509-ca-cert",
                    headers={"Content-Disposition": 'attachment; filename="Librairie-CA.crt"'})

@router.get("/api/qr")
def qr_svg(data: str):
    """QR code généré localement : l'URL d'appairage ne quitte jamais le poste (aucun service tiers)."""
    if not data.startswith("https://") or len(data) > 300:
        raise HTTPException(400, "Donnée invalide")
    import segno
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=8, border=2, dark="#000000", light="#ffffff")
    return Response(buf.getvalue(), media_type="image/svg+xml")
