"""
app/routers/__init__.py
-------------------------------------------------------------------------------
Paquet des routeurs modulaires de l'application FastAPI.
-------------------------------------------------------------------------------
"""

from . import books, sales, receptions, ocr, sync, reports, options

__all__ = [
    "books",
    "sales",
    "receptions",
    "ocr",
    "sync",
    "reports",
    "options",
]
