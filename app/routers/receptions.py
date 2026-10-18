"""
app/routers/receptions.py
-------------------------------------------------------------------------------
Routeur FastAPI dédié aux réceptions de stock, créations de lots et ajustements d'inventaire.
-------------------------------------------------------------------------------
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from .. import db

router = APIRouter(prefix="/api", tags=["receptions"])

DATE_PATTERN = r"^(\d{4}-\d{2}-\d{2})?$"


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


def _broadcast(event_type: str, data: dict):
    from ..main import live_hub
    live_hub.broadcast(event_type, data)


class LotIn(BaseModel):
    book_id: int
    owner_id: int
    qty_in: int = Field(ge=1, le=100000)
    date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    unit_cost: Optional[float] = Field(None, ge=0, le=100000)
    reverse_pct: Optional[float] = Field(None, ge=0, le=100)
    note: Optional[str] = Field(None, max_length=300)


class AdjIn(BaseModel):
    delta: int = Field(ge=-100000, le=100000)
    reason: Optional[str] = Field("Ajustement", max_length=300)
    date: Optional[str] = Field(None, pattern=DATE_PATTERN)


@router.post("/lots")
def lot_add(l: LotIn, request: Request):
    user = get_current_user(request)
    with db.tx() as c:
        cur = c.execute("INSERT INTO lots(book_id,owner_id,date,qty_in,unit_cost,reverse_pct,note) VALUES(?,?,?,?,?,?,?)",
                        (l.book_id, l.owner_id, l.date or date.today().isoformat(), l.qty_in, l.unit_cost, l.reverse_pct, l.note))
        lid = cur.lastrowid
        bk = c.execute("SELECT title FROM books WHERE id=?", (l.book_id,)).fetchone()
        ow = c.execute("SELECT name FROM owners WHERE id=?", (l.owner_id,)).fetchone()
        db.log_audit(c, user, "INSERT", "lot", lid,
                     f"Entrée stock : {l.qty_in}× « {bk['title'] if bk else l.book_id} » ({ow['name'] if ow else l.owner_id})",
                     snapshot_after=_dump(l) | {"id": lid})
    _broadcast("activity_logged", {
        "type": "stock_added",
        "user_name": user,
        "title": bk["title"] if bk else f"Livre #{l.book_id}",
        "detail": f"+{l.qty_in} ex. ({ow['name'] if ow else 'Rayon'})",
        "data": {"book_id": l.book_id, "qty": l.qty_in}
    })
    _broadcast("metrics_invalidated", {"reason": "stock_updated"})
    return {"ok": True}


@router.post("/lots/{lid}/adjust")
def lot_adjust(lid: int, a: AdjIn, request: Request):
    user = get_current_user(request)
    with db.tx() as c:
        lot = c.execute("SELECT * FROM lots WHERE id=?", (lid,)).fetchone()
        bk = c.execute("SELECT title FROM books WHERE id=?", (lot['book_id'],)).fetchone() if lot else None
        cur = c.execute("INSERT INTO adjustments(lot_id,date,delta,reason) VALUES(?,?,?,?)",
                        (lid, a.date or date.today().isoformat(), a.delta, a.reason))
        jid = cur.lastrowid
        db.log_audit(c, user, "INSERT", "adjustment", jid,
                     f"Ajustement stock ({'+' if a.delta > 0 else ''}{a.delta}) « {bk['title'] if bk else ''} » : {a.reason}",
                     snapshot_after={"id": jid, "lot_id": lid, "delta": a.delta, "reason": a.reason})
    _broadcast("activity_logged", {
        "type": "stock_adjusted",
        "user_name": user,
        "title": bk["title"] if bk else "Livre",
        "detail": f"Ajustement {'+' if a.delta > 0 else ''}{a.delta} ({a.reason})",
        "data": {"lot_id": lid, "delta": a.delta}
    })
    _broadcast("metrics_invalidated", {"reason": "stock_updated"})
    return {"ok": True}
