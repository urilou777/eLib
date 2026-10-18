"""
app/routers/ocr.py
-------------------------------------------------------------------------------
Routeur FastAPI dédié aux opérations d'OCR haute fidélité (vision, couverture, page de garde).
-------------------------------------------------------------------------------
"""

import json
import base64
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from .. import ocr

router = APIRouter(prefix="/api/ocr", tags=["ocr"])


class OcrScanIn(BaseModel):
    image_base64: str


@router.post("/scan")
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
