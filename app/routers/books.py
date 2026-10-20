"""Books API routes."""

from fastapi import APIRouter
import json
from fastapi import HTTPException, Request
from .. import db, ocr
from ..api_common import dump_model as _dump, get_current_user
from ..schemas import BookIn
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
