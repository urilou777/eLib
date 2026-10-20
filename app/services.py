"""Shared application state and services used by API routers."""

import os
import re
import threading
import time
import shutil
from datetime import datetime
from fastapi import HTTPException
from typing import Optional
from . import certs, db, excel_io, security

db.init()

MIRROR = os.path.join(db.DATA_DIR, "Bibliotheque_miroir.xlsx")

BACKUPS = os.path.join(db.DATA_DIR, "sauvegardes")

os.makedirs(BACKUPS, exist_ok=True)

_dirty = threading.Event()

def cleanup_old_backups(max_hourly: int = 24, max_daily: int = 30, max_pre_ops: int = 10) -> int:
    """Politique de rétention intelligente de l'espace disque :
    - Conserve les 30 derniers snapshots quotidiens (YYYY-MM-DD) + tous les 1ers du mois (archives permanentes).
    - Conserve les 24 derniers snapshots horaires (YYYYMMDD_HHMM).
    - Conserve les 10 derniers snapshots pré-opérations (avant_renommage_*, librairie_backup_pre_*).
    Retourne le nombre de fichiers purgés.
    """
    if not os.path.exists(BACKUPS):
        return 0
    deleted_count = 0

    hourly_pattern = re.compile(r"^librairie_(\d{8})_(\d{4}|\d{6})\.db$")
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

    # 1. Purge des instantanés horaires : ne garder que les `max_hourly` plus récents
    hourly_files.sort(key=lambda x: x[1], reverse=True)
    for fpath, _ in hourly_files[max_hourly:]:
        try:
            os.remove(fpath)
            deleted_count += 1
        except OSError:
            pass

    # 2. Purge des instantanés pré-opérations : ne garder que les `max_pre_ops` plus récents
    pre_op_files.sort(key=lambda x: x[1], reverse=True)
    for fpath, _ in pre_op_files[max_pre_ops:]:
        try:
            os.remove(fpath)
            deleted_count += 1
        except OSError:
            pass

    # 3. Purge des exports Excel manuels anciens : garder les 10 plus récents
    manual_xl_files.sort(key=lambda x: x[1], reverse=True)
    for fpath, _ in manual_xl_files[10:]:
        try:
            os.remove(fpath)
            deleted_count += 1
        except OSError:
            pass

    # 4. Purge des sauvegardes journalières .db : garder les `max_daily` plus récents OU le 1er du mois
    daily_db_files.sort(key=lambda x: x[1], reverse=True)
    for idx, (fpath, _, is_first_of_month) in enumerate(daily_db_files):
        if idx >= max_daily and not is_first_of_month:
            try:
                os.remove(fpath)
                deleted_count += 1
            except OSError:
                pass

    # 5. Purge des sauvegardes journalières .xlsx : garder les `max_daily` plus récents OU le 1er du mois
    daily_xl_files.sort(key=lambda x: x[1], reverse=True)
    for idx, (fpath, _, is_first_of_month) in enumerate(daily_xl_files):
        if idx >= max_daily and not is_first_of_month:
            try:
                os.remove(fpath)
                deleted_count += 1
            except OSError:
                pass

    return deleted_count

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
                # 1. Écriture atomique du miroir Excel
                excel_io.export_workbook(MIRROR)

                # 2. Sauvegarde SQLite atomique à chaud (anti-corruption même si coupure de courant pendant l'écriture)
                daily_db = os.path.join(BACKUPS, f"librairie_{today}.db")
                db.safe_backup_db(daily_db)

                # 3. Snapshot miroir journalier
                daily_xl = os.path.join(BACKUPS, f"Bibliotheque_{today}.xlsx")
                tmp_xl = daily_xl + ".tmp"
                shutil.copyfile(MIRROR, tmp_xl)
                os.replace(tmp_xl, daily_xl)

                # 4. Snapshots glissants récents (toutes les heures en cas d'activité)
                if time.time() - last_hourly_backup > 3600 or last_day != today:
                    stamp = now.strftime("%Y%m%d_%H%M")
                    db.safe_backup_db(os.path.join(BACKUPS, f"librairie_{stamp}.db"))
                    last_hourly_backup = time.time()
                    cleanup_old_backups()

                # 5. Rétention automatique lors du passage au jour suivant
                if last_day != today:
                    cleanup_old_backups()

                last_day = today
            except Exception as e:
                print("Erreur boucle de sauvegarde résiliente:", e)

FIXED_OWNERS = {"cité royale", "icc rennes"}

def _books(c, where="1=1", args=()):
    bl = db.rows(c, f"""SELECT b.*, COALESCE((SELECT SUM({db.LOT_REMAINING}) FROM lots l WHERE l.book_id=b.id),0) stock
        FROM books b WHERE b.active=1 AND {where} ORDER BY b.is_pack DESC, b.series, b.title, b.volume""", args)
    byo, lots_by = {}, {}
    for r in db.rows(c, f"""SELECT l.id, l.book_id, l.date, o.name owner, o.color, ({db.LOT_REMAINING}) remaining
            FROM lots l JOIN owners o ON o.id=l.owner_id ORDER BY l.date, l.id"""):
        if r["remaining"] > 0:
            lots_by.setdefault(r["book_id"], []).append(r)
    for r in db.rows(c, f"""SELECT l.book_id, o.name, o.color, SUM({db.LOT_REMAINING}) rem FROM lots l
            JOIN owners o ON o.id=l.owner_id GROUP BY l.book_id, o.id"""):
        if r["rem"]:
            byo.setdefault(r["book_id"], []).append({"owner": r["name"], "color": r["color"], "qty": r["rem"]})
    packs_by_book = {}
    for r in db.rows(c, """
        SELECT pi.book_id, p.id pack_id, p.code pack_code, p.title pack_title, p.price pack_price,
               (SELECT SUM(bk.price * pi2.qty) FROM pack_items pi2 JOIN books bk ON bk.id = pi2.book_id WHERE pi2.pack_id = p.id) separate_price,
               (SELECT GROUP_CONCAT(bk2.title, ' + ') FROM pack_items pi3 JOIN books bk2 ON bk2.id = pi3.book_id WHERE pi3.pack_id = p.id AND bk2.id != pi.book_id) other_items
        FROM pack_items pi
        JOIN books p ON p.id = pi.pack_id
        WHERE p.active = 1
    """):
        saving = round(float(r["separate_price"] or 0) - float(r["pack_price"] or 0), 2)
        packs_by_book.setdefault(r["book_id"], []).append({
            "id": r["pack_id"],
            "code": r["pack_code"],
            "title": r["pack_title"],
            "price": r["pack_price"],
            "separate_price": r["separate_price"],
            "other_items": r["other_items"] or "",
            "saving": saving
        })

    for b in bl:
        b["by_owner"] = byo.get(b["id"], [])
        b["lots"] = lots_by.get(b["id"], [])
        if b["is_pack"]:
            b["stock"] = db.pack_stock(c, b["id"])
            b["items"] = db.rows(c, """SELECT pi.book_id,pi.qty,bk.title FROM pack_items pi
                JOIN books bk ON bk.id=pi.book_id WHERE pi.pack_id=?""", (b["id"],))
            for it in b["items"]:
                it["lots"] = lots_by.get(it["book_id"], [])
            b["suggested_packs"] = []
        else:
            s_packs = packs_by_book.get(b["id"], [])
            for sp in s_packs:
                sp["stock"] = db.pack_stock(c, sp["id"])
            b["suggested_packs"] = s_packs
    return bl

def _forecast(vals, n=3):
    k = len(vals)
    if k < 2:
        return [vals[-1] if vals else 0] * n
    xs = list(range(k))
    mx, my = sum(xs) / k, sum(vals) / k
    den = sum((x - mx) ** 2 for x in xs) or 1
    a = sum((x - mx) * (y - my) for x, y in zip(xs, vals)) / den
    b = my - a * mx
    return [max(0, a * (k + i) + b) for i in range(n)]

MATRIX_DIMENSIONS = {
    "moment": {
        "label": "Culte / Temps de vente",
        "expr": "COALESCE(s.service_moment, CASE WHEN s.note = 'Import Excel' THEN 'Import historique' ELSE 'Non précisé' END)",
    },
    "age": {
        "label": "Tranche d'Âge",
        "expr": "COALESCE(s.customer_age_group, CASE WHEN s.note = 'Import Excel' THEN 'Import historique' ELSE 'Non renseigné' END)",
    },
    "gender": {
        "label": "Genre",
        "expr": "COALESCE(s.customer_gender, CASE WHEN s.note = 'Import Excel' THEN 'Import historique' ELSE 'Non renseigné' END)",
    },
    "star": {
        "label": "Serviteur STAR",
        "expr": "CASE WHEN s.is_star = 1 THEN 'Serviteurs STAR ⭐' ELSE 'Autres fidèles & Visiteurs' END",
    },
    "category": {
        "label": "Catégorie / Rayon",
        "expr": "COALESCE(b.category, 'Non catégorisé')",
    },
    "publisher": {
        "label": "Éditeur",
        "expr": "COALESCE(b.publisher, 'Non renseigné')",
    },
    "payment": {
        "label": "Mode de Paiement",
        "expr": "COALESCE(s.payment, 'Non renseigné')",
    },
    "owner": {
        "label": "Origine du Stock",
        "expr": "COALESCE(o.name, 'Sans stock')",
    },
    "weekday": {
        "label": "Jour de la Semaine",
        "expr": "CASE CAST(strftime('%w', s.date) AS INT) WHEN 0 THEN '0. Dimanche' WHEN 1 THEN '1. Lundi' WHEN 2 THEN '2. Mardi' WHEN 3 THEN '3. Mercredi' WHEN 4 THEN '4. Jeudi' WHEN 5 THEN '5. Vendredi' WHEN 6 THEN '6. Samedi' END",
    },
    "month": {
        "label": "Mois de Vente",
        "expr": "strftime('%Y-%m', s.date)",
    }
}

MATRIX_ALIASES = {
    "service_moment": "moment",
    "customer_age_group": "age",
    "age_group": "age",
    "customer_gender": "gender",
    "is_star": "star",
}

MAX_IMPORT_BYTES = 25 * 1024 * 1024

MAX_UNZIPPED_BYTES = 200 * 1024 * 1024

BACKUP_NAME = re.compile(r"^[A-Za-z0-9_\-]{1,120}\.(db|xlsx)$")

def backup_path(filename: str) -> str:
    """Chemin sûr d'un fichier de sauvegarde : nom strict + confinement dans le dossier des sauvegardes.
    Bloque la traversée de répertoires (« ..\\ », « ../ », chemins absolus, ADS Windows, etc.)."""
    if not BACKUP_NAME.fullmatch(filename or ""):
        raise HTTPException(400, "Nom de fichier de sauvegarde invalide")
    root = os.path.realpath(BACKUPS)
    path = os.path.realpath(os.path.join(root, filename))
    if os.path.commonpath([root, path]) != root or os.path.dirname(path) != root:
        raise HTTPException(400, "Nom de fichier de sauvegarde invalide")
    return path

MASTER_SESSION_MOMENT: Optional[str] = None

def get_current_moment() -> str:
    if MASTER_SESSION_MOMENT:
        return MASTER_SESSION_MOMENT
    now = datetime.now()
    if now.weekday() == 6:  # Dimanche
        return "2e Culte (Jeunes EJP)" if now.hour >= 12 else "1er Culte (Principal)"
    return "En semaine / Autre"


def get_master_session_moment() -> Optional[str]:
    return MASTER_SESSION_MOMENT


def set_master_session_moment(moment: Optional[str]) -> None:
    global MASTER_SESSION_MOMENT
    MASTER_SESSION_MOMENT = moment


def _mobile_base():
    port, ips = security.state["https_port"], security.local_ips()
    return f"https://{ips[0]}:{port}" if (port and ips and certs) else None

def _mobile_book(c, b):
    if b["is_pack"]:
        stock = db.pack_stock(c, b["id"])
        items = db.rows(c, """SELECT pi.book_id, pi.qty, bk.title, bk.price FROM pack_items pi
            JOIN books bk ON bk.id=pi.book_id WHERE pi.pack_id=?""", (b["id"],))
        for it in items:
            it["lots"] = db.rows(c, f"""
                SELECT l.id, l.date, o.name owner, o.color, ({db.LOT_REMAINING}) remaining
                FROM lots l JOIN owners o ON o.id=l.owner_id
                WHERE l.book_id=? AND ({db.LOT_REMAINING}) > 0
                ORDER BY o.priority, l.date, l.id""", (it["book_id"],))
        return {
            "id": b["id"], "code": b["code"], "title": b["title"], "volume": b["volume"], "price": b["price"],
            "is_pack": 1, "lots": [], "stock": stock, "items": items, "suggested_packs": []
        }

    lots = db.rows(c, f"""
        SELECT l.id, l.date, o.name owner, o.color, ({db.LOT_REMAINING}) remaining
        FROM lots l JOIN owners o ON o.id=l.owner_id
        WHERE l.book_id=? AND ({db.LOT_REMAINING}) > 0
        ORDER BY o.priority, l.date, l.id""", (b["id"],))

    raw_packs = db.rows(c, """
        SELECT p.id, p.code, p.title, p.price,
               (SELECT SUM(bk.price * pi2.qty) FROM pack_items pi2 JOIN books bk ON bk.id = pi2.book_id WHERE pi2.pack_id = p.id) separate_price,
               (SELECT GROUP_CONCAT(bk2.title, ' + ') FROM pack_items pi3 JOIN books bk2 ON bk2.id = pi3.book_id WHERE pi3.pack_id = p.id AND bk2.id != ?) other_items
        FROM pack_items pi
        JOIN books p ON p.id = pi.pack_id
        WHERE pi.book_id = ? AND p.active = 1
    """, (b["id"], b["id"]))

    suggested_packs = []
    for sp in raw_packs:
        sp_stock = db.pack_stock(c, sp["id"])
        saving = round(float(sp["separate_price"] or 0) - float(sp["price"] or 0), 2)
        sp_items = db.rows(c, """SELECT pi.book_id, pi.qty, bk.title, bk.price FROM pack_items pi
            JOIN books bk ON bk.id=pi.book_id WHERE pi.pack_id=?""", (sp["id"],))
        for it in sp_items:
            it["lots"] = db.rows(c, f"""
                SELECT l.id, l.date, o.name owner, o.color, ({db.LOT_REMAINING}) remaining
                FROM lots l JOIN owners o ON o.id=l.owner_id
                WHERE l.book_id=? AND ({db.LOT_REMAINING}) > 0
                ORDER BY o.priority, l.date, l.id""", (it["book_id"],))
        suggested_packs.append({
            "id": sp["id"],
            "code": sp["code"],
            "title": sp["title"],
            "price": sp["price"],
            "separate_price": sp["separate_price"],
            "other_items": sp["other_items"] or "",
            "saving": saving,
            "stock": sp_stock,
            "is_pack": 1,
            "items": sp_items
        })

    return {
        "id": b["id"], "code": b["code"], "title": b["title"], "volume": b["volume"], "price": b["price"],
        "is_pack": 0, "lots": lots, "stock": sum(l["remaining"] for l in lots),
        "suggested_packs": suggested_packs
    }
