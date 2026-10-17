"""Sécurité réseau : rôles (poste vs téléphone), appairage des appareils, contrôles HTTP.

Modèle de menace : le PC est branché sur un Wi-Fi partagé (église = invités possibles).
- Le poste de caisse (loopback 127.0.0.1) a tous les droits.
- Un téléphone du réseau local n'a accès qu'à une liste blanche minimale (scan + vente) ET uniquement
  s'il a été appairé par QR code (jeton aléatoire 256 bits, stocké haché, révocable depuis le PC).
- Les adresses non privées (Internet) sont refusées d'office.
- Contrôles Host / Origin / Sec-Fetch-Site contre le DNS-rebinding et le CSRF.
- En-têtes de sécurité (CSP, nosniff, anti-framing, Permissions-Policy limitant la caméra à /mobile).
"""
import hashlib
import ipaddress
import os
import re
import secrets
import socket
import sqlite3
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

from . import db

# Port HTTPS effectivement ouvert (renseigné par run.py) ; None = mode poste seul, sans mobile
state = {"https_port": None}

# Les appairages sont dans un fichier SÉPARÉ de la base métier : restaurer une sauvegarde ne peut donc
# jamais « ressusciter » un téléphone révoqué (ni en effacer un légitime).
DEVICES_DB = os.path.join(db.DATA_DIR, "devices.db")


@contextmanager
def _dev():
    c = sqlite3.connect(DEVICES_DB, timeout=15)
    c.row_factory = sqlite3.Row
    try:
        c.execute("""CREATE TABLE IF NOT EXISTS devices(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL, last_seen TEXT, last_ip TEXT, revoked INTEGER NOT NULL DEFAULT 0)""")
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
PAIRING_TTL = 300  # 5 minutes

# ---------- adresses locales ----------
_ip_cache = {"t": 0, "v": []}


def local_ips():
    """IPv4 privées de la machine (l'IP de sortie principale en premier)."""
    if time.time() - _ip_cache["t"] < 30 and _ip_cache["v"]:
        return _ip_cache["v"]
    found = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        found.append(s.getsockname()[0])
    except Exception:
        pass
    finally:
        s.close()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except Exception:
        pass
    out = []
    for ip in found:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if a.is_private and not a.is_loopback and not a.is_link_local and ip not in out:
            out.append(ip)
    _ip_cache.update(t=time.time(), v=out)
    return out


def allowed_hosts():
    hosts = set(LOOPBACK) | set(local_ips())
    name = socket.gethostname().lower()
    hosts |= {name, f"{name}.local"}
    return hosts


def _host_only(host_header):
    h = (host_header or "").strip().lower()
    if h.startswith("["):                       # IPv6 littéral [::1]:8765
        return h[1:].split("]")[0]
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def is_loopback(request: Request):
    c = request.client
    return bool(c) and c.host in LOOPBACK


# ---------- limitation de débit (échecs d'authentification / appairage) ----------
_fails = defaultdict(deque)
_fail_lock = threading.Lock()
FAIL_MAX, FAIL_WINDOW = 10, 60


def _blocked(ip):
    now = time.time()
    with _fail_lock:
        q = _fails[ip]
        while q and now - q[0] > FAIL_WINDOW:
            q.popleft()
        return len(q) >= FAIL_MAX


def register_failure(ip):
    with _fail_lock:
        _fails[ip].append(time.time())


# ---------- appairage ----------
_codes = {}              # code -> expiration (epoch)
_codes_lock = threading.Lock()


def new_pairing_code():
    code = secrets.token_urlsafe(12)
    now = time.time()
    with _codes_lock:
        for k in [k for k, exp in _codes.items() if exp < now]:
            del _codes[k]
        _codes[code] = now + PAIRING_TTL
    return code


def _consume_code(code):
    now = time.time()
    with _codes_lock:
        exp = _codes.pop(code, 0)      # usage unique : retiré dès la première tentative valide
    return exp >= now


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def redeem_pairing(code, name, ip):
    """Échange un code d'appairage contre un jeton d'appareil. Retourne le jeton ou None."""
    if _blocked(ip) or not code or not _consume_code(code):
        register_failure(ip)
        return None
    token = secrets.token_urlsafe(32)
    clean = re.sub(r"[\x00-\x1f<>\"']", "", (name or "Téléphone"))[:60].strip() or "Téléphone"
    with _dev() as c:
        c.execute("INSERT INTO devices(name,token_hash,created_at,last_ip) VALUES(?,?,?,?)",
                  (clean, _hash(token), datetime.now().isoformat(timespec="seconds"), ip))
    return token


_last_seen = {}


def device_from_request(request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    if not (20 <= len(token) <= 100):
        return None
    ip = request.client.host if request.client else "?"
    with _dev() as c:
        row = c.execute("SELECT id,name FROM devices WHERE token_hash=? AND revoked=0", (_hash(token),)).fetchone()
        if row:
            if time.time() - _last_seen.get(row["id"], 0) > 60:      # écriture au plus 1×/min
                _last_seen[row["id"]] = time.time()
                c.execute("UPDATE devices SET last_seen=?, last_ip=? WHERE id=?",
                          (datetime.now().isoformat(timespec="seconds"), ip, row["id"]))
            return {"id": row["id"], "name": row["name"]}
    return None


def list_devices():
    with _dev() as c:
        return [dict(r) for r in c.execute(
            "SELECT id,name,created_at,last_seen,last_ip FROM devices WHERE revoked=0 ORDER BY id DESC")]


def revoke_device(did):
    with _dev() as c:
        c.execute("UPDATE devices SET revoked=1 WHERE id=?", (did,))
    _last_seen.pop(did, None)


# ---------- politique d'accès ----------
# Accessible depuis le réseau local SANS jeton (ressources publiques, aucune donnée métier)
PUBLIC = [
    ("GET", re.compile(r"^/mobile$")),
    ("GET", re.compile(r"^/static/(mobile\.js|sw\.js|manifest\.webmanifest|icon\.svg|fonts\.css|favicon.*|fonts/.*|img/.*|vendor/zxing\.min\.js)$")),
    ("GET", re.compile(r"^/api/ca\.crt$")),
    ("GET", re.compile(r"^/api/ping$")),
    ("GET", re.compile(r"^/api/live/stream$")),
    ("GET", re.compile(r"^/api/live/baskets$")),
    ("POST", re.compile(r"^/api/live/activity$")),
    ("POST", re.compile(r"^/api/mobile/pair$")),
]
# Accessible depuis le réseau local AVEC jeton d'appareil valide (privilège minimal : scanner, vendre, réceptionner)
MOBILE = [
    ("GET", re.compile(r"^/api/mobile/me$")),
    ("GET", re.compile(r"^/api/users$")),
    ("GET", re.compile(r"^/api/options$")),
    ("GET", re.compile(r"^/api/owners$")),
    ("GET", re.compile(r"^/api/books/scan/[^/]+$")),
    ("GET", re.compile(r"^/api/books/\d+/stats$")),
    ("GET", re.compile(r"^/api/books/search$")),
    ("GET", re.compile(r"^/api/live/stream$")),
    ("GET", re.compile(r"^/api/live/baskets$")),
    ("POST", re.compile(r"^/api/live/activity$")),
    ("POST", re.compile(r"^/api/mobile/active-cart$")),
    ("DELETE", re.compile(r"^/api/mobile/active-cart$")),
    ("POST", re.compile(r"^/api/books$")),
    ("POST", re.compile(r"^/api/lots$")),
    ("POST", re.compile(r"^/api/sales$")),
]


def _match(rules, method, path):
    return any(m == method and rx.match(path) for m, rx in rules)


MAX_BODY = 1 * 1024 * 1024
MAX_IMPORT_BODY = 26 * 1024 * 1024

CSP_APP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
           "img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; "
           "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
CSP_MOBILE = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
              "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; manifest-src 'self'; "
              "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def _deny(status, msg, headers=None):
    return JSONResponse({"detail": msg}, status_code=status, headers=headers or {})


def _secure(resp, path, https):
    mobile = path == "/mobile" or path.startswith("/api/mobile") or path.startswith("/static/mobile") \
        or path.startswith("/static/vendor")
    resp.headers["Content-Security-Policy"] = CSP_MOBILE if mobile else CSP_APP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resp.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    # La caméra n'est autorisée que sur l'écran mobile ; tout le reste est coupé.
    resp.headers["Permissions-Policy"] = ("camera=(self), " if path == "/mobile" else "camera=(), ") + \
        "microphone=(), geolocation=(), payment=(), usb=(), serial=(), bluetooth=(), interest-cohort=()"
    if path.startswith("/api/") and path != "/api/ca.crt":
        resp.headers["Cache-Control"] = "no-store"
    if https:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000"
    return resp


async def security_gate(request: Request, call_next):
    path, method = request.url.path, request.method
    https = request.url.scheme == "https"
    client_ip = request.client.host if request.client else "?"
    loop = is_loopback(request)

    # 1. Origine réseau : loopback ou réseau privé uniquement
    if not loop:
        try:
            if not ipaddress.ip_address(client_ip).is_private:
                return _deny(403, "Accès refusé (hors réseau local)")
        except ValueError:
            return _deny(403, "Accès refusé")

    # 2. Host : bloque le DNS-rebinding (un site web hostile qui résout vers 127.0.0.1 / l'IP du PC)
    if _host_only(request.headers.get("host")) not in allowed_hosts():
        return _deny(421, "Hôte non autorisé")

    # 3. Anti-CSRF pour les méthodes qui modifient l'état
    if method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc.lower() != (request.headers.get("host") or "").lower():
            return _deny(403, "Origine refusée")
        if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
            return _deny(403, "Requête inter-sites refusée")
        try:
            size = int(request.headers.get("content-length") or 0)
        except ValueError:
            return _deny(400, "Content-Length invalide")
        limit = MAX_IMPORT_BODY if path == "/api/import" else MAX_BODY
        if size > limit:
            return _deny(413, "Requête trop volumineuse")

    # 4. Contrôle d'accès par rôle
    request.state.role = "desk"
    request.state.device = None
    if not loop and not _match(PUBLIC, method, path):
        if _blocked(client_ip):
            return _deny(429, "Trop de tentatives, réessayez dans une minute", {"Retry-After": "60"})
        dev = device_from_request(request)
        if not dev:
            register_failure(client_ip)
            return _deny(401, "Appareil non appairé : scannez le QR code affiché sur le poste de caisse")
        if not _match(MOBILE, method, path):
            return _deny(403, "Action réservée au poste de caisse")
        request.state.role, request.state.device = "mobile", dev
    elif not loop:
        request.state.role = "public"

    resp = await call_next(request)
    return _secure(resp, path, https)
