"""Shared API helpers used by domain routers."""

import re
from urllib.parse import unquote

from fastapi import HTTPException, Request

from . import db


def dump_model(model):
    """Serialize a Pydantic v1 or v2 model without deprecation warnings."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model)


def get_current_user(request: Request) -> str:
    """Read and sanitize the active operator supplied by the client."""
    raw = request.headers.get("X-User") or request.query_params.get("user") or ""
    user = re.sub(r"[\x00-\x1f\x7f<>]", "", unquote(raw)).strip()[:60]
    return user or "Anonyme"


def require_known_user(request: Request) -> str:
    """Require mobile devices to select an existing cashier profile."""
    user = get_current_user(request)
    if getattr(request.state, "role", "desk") == "mobile":
        with db.tx() as connection:
            if not connection.execute(
                "SELECT 1 FROM users WHERE name=?", (user,)
            ).fetchone():
                raise HTTPException(
                    400,
                    "Profil libraire inconnu : choisissez votre prénom dans la liste",
                )
    return user
