"""Books API routes."""

import json
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from .. import db
from ..api_common import dump_model as _dump, get_current_user
from ..schemas import BookEnrichIn, BookIn
from ..services import _books, _mobile_book

router = APIRouter()

@router.get("/api/books")
def books():
    with db.tx() as c:
        return _books(c)

@router.post("/api/books")
def book_add(b: BookIn, request: Request):
    with db.tx() as c:
        try:
            cur = c.execute("""INSERT INTO books(code,title,series,volume,author,publisher,category,type,location,price,min_stock,is_pack)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (b.code, b.title, b.series, b.volume, b.author, b.publisher,
                                                     b.category, b.type, b.location, b.price, b.min_stock, b.is_pack))
            bid = cur.lastrowid
            db.log_audit(c, get_current_user(request), "INSERT", "book", bid, f"Création livre « {b.title} » ({b.code})", snapshot_after=_dump(b) | {"id": bid})
            return {"id": bid}
        except Exception:
            raise HTTPException(400, "Ce code existe déjà")

@router.put("/api/books/{bid}")
def book_upd(bid: int, b: BookIn, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
        if not old:
            raise HTTPException(404, "Livre introuvable")
        c.execute("""UPDATE books SET code=?,title=?,series=?,volume=?,author=?,publisher=?,category=?,type=?,
            location=?,price=?,min_stock=? WHERE id=?""", (b.code, b.title, b.series, b.volume, b.author,
                                                           b.publisher, b.category, b.type, b.location, b.price, b.min_stock, bid))
        db.log_audit(c, get_current_user(request), "UPDATE", "book", bid, f"Modification fiche « {b.title} »", snapshot_before=dict(old), snapshot_after=_dump(b) | {"id": bid})
    return {"ok": True}


@router.post("/api/books/{bid}/enrich")
def book_enrich(bid: int, patch: BookEnrichIn, request: Request):
    """Complète les champs absents d'une fiche existante sans écraser ses données."""
    with db.tx(immediate=True) as c:
        old = c.execute("SELECT * FROM books WHERE id=? AND active=1", (bid,)).fetchone()
        if not old:
            raise HTTPException(404, "Livre introuvable")

        updates = {}
        incoming = _dump(patch)
        incoming_title = (incoming.get("title") or "").strip()
        if not (old["title"] or "").strip() and not incoming_title:
            raise HTTPException(422, "Le titre est requis pour compléter cette fiche")

        new_code = (incoming.get("code") or "").strip()
        old_code = (old["code"] or "").strip()
        if new_code:
            if old_code and old_code != new_code:
                raise HTTPException(
                    409,
                    "Cette fiche possède déjà un autre code-barres. "
                    "Le remplacement automatique est refusé.",
                )
            if not old_code:
                updates["code"] = new_code

        for field in ("title", "series", "volume", "author", "publisher"):
            value = incoming.get(field)
            if value is not None and str(value).strip() and not str(old[field] or "").strip():
                updates[field] = str(value).strip()

        price = incoming.get("price")
        if price is not None and float(old["price"] or 0) <= 0 and price > 0:
            updates["price"] = price

        before = dict(old)
        if updates:
            assignments = ", ".join(f"{field}=?" for field in updates)
            try:
                c.execute(
                    f"UPDATE books SET {assignments} WHERE id=?",
                    (*updates.values(), bid),
                )
            except sqlite3.IntegrityError as error:
                raise HTTPException(409, "Ce code-barres est déjà associé à un autre livre") from error
            after = dict(c.execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone())
            db.log_audit(
                c,
                get_current_user(request),
                "UPDATE",
                "book",
                bid,
                f"Complément de la fiche « {after['title']} » : {', '.join(updates)}",
                snapshot_before=before,
                snapshot_after=after,
            )
        else:
            after = before

        return {"ok": True, "id": bid, "updated": list(updates), "book": after}


@router.post("/api/ocr/scan")
async def ocr_scan(request: Request):
    """
    Analyse une image de page de garde ou de couverture de livre par OCR local (RapidOCR).
    Supporte de manière transparente :
    - JSON : {"image_base64": "..."} ou {"image": "..."}
    - Multipart FormData : champ 'file' ou 'image'
    - Corps brut binaire
    """
    content_type = (request.headers.get("content-type") or "").lower()
    img_bytes = None

    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
            uploaded = form.get("file") or form.get("image")
            if uploaded and hasattr(uploaded, "read"):
                img_bytes = await uploaded.read()
        except Exception as e:
            raise HTTPException(400, f"Erreur lecture multipart : {e}")
    elif "application/json" in content_type:
        try:
            data = await request.json()
            raw_b64 = data.get("image_base64") or data.get("image") or data.get("data") or ""
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            if raw_b64:
                import base64
                img_bytes = base64.b64decode(raw_b64)
        except Exception as e:
            raise HTTPException(400, f"Erreur décodage JSON / base64 : {e}")
    else:
        # Tenter d'abord JSON puis binaire direct
        body_bytes = await request.body()
        if body_bytes.startswith(b"{"):
            try:
                data = json.loads(body_bytes.decode("utf-8", errors="ignore"))
                raw_b64 = data.get("image_base64") or data.get("image") or ""
                if "," in raw_b64:
                    raw_b64 = raw_b64.split(",", 1)[1]
                if raw_b64:
                    import base64
                    img_bytes = base64.b64decode(raw_b64)
            except Exception:
                pass
        if not img_bytes and body_bytes:
            img_bytes = body_bytes

    if not img_bytes:
        raise HTTPException(400, "Aucune image reçue pour l'analyse OCR")

    from .. import ocr  # import différé : numpy/PIL/RapidOCR ne doivent pas ralentir le démarrage
    try:
        result = ocr.scan_book_page(img_bytes)
        if not result.get("ok"):
            raise HTTPException(500, result.get("error", "Erreur lors de l'OCR"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur OCR : {str(e)}")

@router.delete("/api/books/{bid}")
def book_del(bid: int, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
        if old:
            c.execute("UPDATE books SET active=0 WHERE id=?", (bid,))
            db.log_audit(c, get_current_user(request), "DELETE", "book", bid, f"Archivage livre « {old['title']} »", snapshot_before=dict(old))
    return {"ok": True}

@router.get("/api/books/scan/{code}")
def scan_book(code: str):
    """Recherche EXACTE par code-barres (ISBN/EAN). Jamais de recherche approximative : un scan ne doit
    pas pouvoir ajouter un mauvais livre au panier."""
    clean = code.strip()[:40]
    plain = clean.replace("-", "").replace(" ", "")
    with db.tx() as c:
        book = c.execute("""SELECT * FROM books WHERE active=1 AND
            (code = ? OR REPLACE(REPLACE(code,'-',''),' ','') = ?) LIMIT 1""", (clean, plain)).fetchone()
        if not book:
            raise HTTPException(404, f"Aucun livre pour le code « {clean} »")
        return _mobile_book(c, book)

@router.get("/api/books/search")
def search_books(q: str):
    """Recherche textuelle (saisie manuelle quand le code-barres est illisible) : 8 résultats maximum."""
    q = q.strip()[:60]
    if len(q) < 2:
        return []
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with db.tx() as c:
        rows = c.execute("""SELECT * FROM books WHERE active=1 AND
            (title LIKE ? ESCAPE '\\' OR code LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\' OR series LIKE ? ESCAPE '\\')
            ORDER BY title LIMIT 8""", (like, like, like, like)).fetchall()
        return [_mobile_book(c, r) for r in rows]
