"""
app/routers/reports.py
-------------------------------------------------------------------------------
Routeur FastAPI dédié aux imports/exports de données et à la gestion des sauvegardes.
-------------------------------------------------------------------------------
"""

import io
import os
import re
import secrets
import shutil
import sqlite3
import zipfile
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse
from .. import db, excel_io

router = APIRouter(prefix="/api", tags=["reports"])

BACKUPS = os.path.join(db.DATA_DIR, "sauvegardes")
os.makedirs(BACKUPS, exist_ok=True)
BACKUP_NAME = re.compile(r"^[A-Za-z0-9_\-]{1,120}\.(db|xlsx)$")

MAX_IMPORT_BYTES = 25 * 1024 * 1024
MAX_UNZIPPED_BYTES = 200 * 1024 * 1024


def get_current_user(request: Request) -> str:
    from urllib.parse import unquote
    raw = request.headers.get("X-User") or request.query_params.get("user") or ""
    u = re.sub(r"[\x00-\x1f\x7f<>]", "", unquote(raw)).strip()[:60]
    return u or "Anonyme"


def backup_path(filename: str) -> str:
    """Chemin sûr d'un fichier de sauvegarde : nom strict + confinement dans le dossier des sauvegardes."""
    if not BACKUP_NAME.fullmatch(filename or ""):
        raise HTTPException(400, "Nom de fichier de sauvegarde invalide")
    root = os.path.realpath(BACKUPS)
    path = os.path.realpath(os.path.join(root, filename))
    if os.path.commonpath([root, path]) != root or os.path.dirname(path) != root:
        raise HTTPException(400, "Nom de fichier de sauvegarde invalide")
    return path


def cleanup_old_backups(max_hourly: int = 24, max_daily: int = 30, max_pre_ops: int = 10) -> int:
    """Politique de rétention intelligente de l'espace disque."""
    if not os.path.exists(BACKUPS):
        return 0

    deleted_count = 0
    hourly_pattern = re.compile(r"^librairie_(\d{8}_\d{4})\.db$")
    daily_db_pattern = re.compile(r"^librairie_(\d{4})-(\d{2})-(\d{2})\.db$")
    daily_xl_pattern = re.compile(r"^Bibliotheque_(\d{4})-(\d{2})-(\d{2})\.xlsx$")
    pre_op_pattern = re.compile(r"^(avant_renommage_|librairie_backup_pre_|librairie_backup_before_).*\.(db|xlsx)$")
    manual_xl_pattern = re.compile(r"^Bibliotheque_(\d{8})_(\d{6})\.xlsx$")

    hourly_files = []
    daily_db_files = []
    daily_xl_files = []
    pre_op_files = []
    manual_xl_files = []

    for fname in os.listdir(BACKUPS):
        fpath = os.path.join(BACKUPS, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            mtime = os.stat(fpath).st_mtime
        except OSError:
            continue

        m_hourly = hourly_pattern.match(fname)
        m_daily_db = daily_db_pattern.match(fname)
        m_daily_xl = daily_xl_pattern.match(fname)
        m_pre_op = pre_op_pattern.match(fname)
        m_manual_xl = manual_xl_pattern.match(fname)

        if m_hourly:
            hourly_files.append((fpath, mtime))
        elif m_daily_db:
            year, month, day = m_daily_db.groups()
            daily_db_files.append((fpath, mtime, day == "01"))
        elif m_daily_xl:
            year, month, day = m_daily_xl.groups()
            daily_xl_files.append((fpath, mtime, day == "01"))
        elif m_pre_op:
            pre_op_files.append((fpath, mtime))
        elif m_manual_xl:
            manual_xl_files.append((fpath, mtime))

    hourly_files.sort(key=lambda x: x[1], reverse=True)
    for fpath, _ in hourly_files[max_hourly:]:
        try:
            os.remove(fpath)
            deleted_count += 1
        except OSError:
            pass

    pre_op_files.sort(key=lambda x: x[1], reverse=True)
    for fpath, _ in pre_op_files[max_pre_ops:]:
        try:
            os.remove(fpath)
            deleted_count += 1
        except OSError:
            pass

    manual_xl_files.sort(key=lambda x: x[1], reverse=True)
    for fpath, _ in manual_xl_files[10:]:
        try:
            os.remove(fpath)
            deleted_count += 1
        except OSError:
            pass

    daily_db_files.sort(key=lambda x: x[1], reverse=True)
    for idx, (fpath, _, is_first_of_month) in enumerate(daily_db_files):
        if idx >= max_daily and not is_first_of_month:
            try:
                os.remove(fpath)
                deleted_count += 1
            except OSError:
                pass

    daily_xl_files.sort(key=lambda x: x[1], reverse=True)
    for idx, (fpath, _, is_first_of_month) in enumerate(daily_xl_files):
        if idx >= max_daily and not is_first_of_month:
            try:
                os.remove(fpath)
                deleted_count += 1
            except OSError:
                pass

    return deleted_count


@router.post("/import")
async def import_xlsx(request: Request, file: UploadFile = File(...), replace: bool = True):
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "Fichier trop volumineux (25 Mo maximum)")
    if not data.startswith(b"PK\x03\x04"):
        raise HTTPException(400, "Ce fichier n'est pas un classeur .xlsx valide")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > 2000 or sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
                raise HTTPException(400, "Classeur rejeté : contenu décompressé anormalement volumineux")
            if "[Content_Types].xml" not in z.namelist():
                raise HTTPException(400, "Ce fichier n'est pas un classeur .xlsx valide")
    except zipfile.BadZipFile:
        raise HTTPException(400, "Fichier .xlsx corrompu")

    tmp = os.path.join(db.DATA_DIR, f"_import_{secrets.token_hex(6)}.xlsx")
    with open(tmp, "wb") as f:
        f.write(data)
    try:
        rep = excel_io.import_workbook(tmp, replace)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "IMPORT", "system", None,
                     f"Import Excel « {os.path.basename(file.filename or 'classeur')[:80]} » (remplacement : {'oui' if replace else 'non'})")
    return rep


@router.get("/export")
def export_xlsx():
    path = os.path.join(db.DATA_DIR, f"Export_{datetime.now():%Y%m%d_%H%M}.xlsx")
    excel_io.export_workbook(path)
    return FileResponse(path, filename=os.path.basename(path),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/backup")
def backup(request: Request):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_db = os.path.join(BACKUPS, f"librairie_{stamp}.db")
    db.safe_backup_db(target_db)

    target_xl = os.path.join(BACKUPS, f"Bibliotheque_{stamp}.xlsx")
    excel_io.export_workbook(target_xl)
    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "BACKUP", "system", None,
                     f"Snapshot manuel créé (librairie_{stamp}.db)")
    return {"ok": True, "filename": f"librairie_{stamp}.db"}


@router.get("/backups")
def list_backups():
    items = []
    if os.path.exists(BACKUPS):
        for fname in os.listdir(BACKUPS):
            if not BACKUP_NAME.fullmatch(fname):
                continue
            fpath = os.path.join(BACKUPS, fname)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                kind = "database" if fname.endswith(".db") else "excel"
                items.append({
                    "filename": fname,
                    "kind": kind,
                    "size_bytes": stat.st_size,
                    "size_human": f"{stat.st_size / 1024:.1f} Ko" if stat.st_size < 1024*1024 else f"{stat.st_size / (1024*1024):.2f} Mo",
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(sep=" ", timespec="seconds")
                })
    items.sort(key=lambda x: x["modified"], reverse=True)
    return items


@router.get("/backups/{filename}/download")
def download_backup(filename: str):
    fpath = backup_path(filename)
    if not os.path.isfile(fpath):
        raise HTTPException(404, "Fichier de sauvegarde introuvable")
    return FileResponse(fpath, filename=filename)


@router.delete("/backups/{filename}")
def delete_backup_file(filename: str, request: Request):
    fpath = backup_path(filename)
    if not os.path.isfile(fpath):
        raise HTTPException(404, "Fichier introuvable")
    os.remove(fpath)
    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "DELETE", "backup", None, f"Suppression fichier de sauvegarde « {filename} »")
    return {"ok": True}


@router.post("/backups/cleanup")
def trigger_backup_cleanup(request: Request):
    purged = cleanup_old_backups()
    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "CLEANUP", "backup", None, f"Purge et rétention des sauvegardes ({purged} fichiers nettoyés)")
    return {"ok": True, "purged": purged}


@router.post("/backups/{filename}/restore")
def restore_backup(filename: str, request: Request):
    if not filename.endswith(".db"):
        raise HTTPException(400, "Seules les sauvegardes de base de données (.db) peuvent être restaurées directement")
    fpath = backup_path(filename)
    if not os.path.isfile(fpath):
        raise HTTPException(404, "Fichier de sauvegarde introuvable")

    tmp_restore = db.DB_PATH + ".tmp_restore"
    shutil.copyfile(fpath, tmp_restore)
    try:
        chk = sqlite3.connect(tmp_restore)
        try:
            ok = chk.execute("PRAGMA quick_check").fetchone()[0] == "ok" and \
                chk.execute("SELECT 1 FROM sqlite_master WHERE name='books'").fetchone() is not None
        finally:
            chk.close()
    except Exception:
        ok = False
    if not ok:
        if os.path.exists(tmp_restore):
            os.remove(tmp_restore)
        raise HTTPException(400, "Sauvegarde corrompue ou invalide : la base actuelle n'a pas été modifiée")

    pre_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_avant_restauration")
    pre_path = os.path.join(BACKUPS, f"librairie_{pre_stamp}.db")
    db.safe_backup_db(pre_path)

    for extra in (db.DB_PATH + "-wal", db.DB_PATH + "-shm"):
        if os.path.exists(extra):
            try:
                os.remove(extra)
            except OSError:
                pass

    os.replace(tmp_restore, db.DB_PATH)

    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "RESTORE", "system", None, f"Restauration depuis « {filename} »")
    return {"ok": True}
