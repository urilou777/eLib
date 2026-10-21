"""Couche base de données (SQLite) + logique métier stock / ventes."""
import sqlite3
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta


def base_dir():
    """Dossier des données : à côté du .exe si empaqueté, sinon dossier du projet."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


DATA_DIR = os.path.abspath(
    os.environ.get("ELIB_DATA_DIR", os.path.join(base_dir(), "data"))
)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "librairie.db")
LATEST_SCHEMA_VERSION = 2


def _migrate_v2(c):
    c.execute(
        "INSERT OR IGNORE INTO app_settings(key, value) VALUES('local_card_enabled', '0')"
    )


SCHEMA_MIGRATIONS = {2: _migrate_v2}

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS owners(
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
  kind TEXT NOT NULL DEFAULT 'maison_mere',      -- maison_mere | locale
  reverse_pct REAL NOT NULL DEFAULT 100,          -- % du prix de vente reversé à l'origine
  priority INTEGER NOT NULL DEFAULT 1,            -- ordre de vente (1 = vendu en premier)
  color TEXT DEFAULT '#6c8cff');
CREATE TABLE IF NOT EXISTS books(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
  series TEXT, volume TEXT, author TEXT, publisher TEXT,
  category TEXT DEFAULT 'Standard', type TEXT, location TEXT,
  price REAL DEFAULT 0, min_stock INTEGER DEFAULT 2,
  is_pack INTEGER DEFAULT 0, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS pack_items(
  pack_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  book_id INTEGER NOT NULL REFERENCES books(id), qty INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(pack_id, book_id));
CREATE TABLE IF NOT EXISTS lots(
  id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id),
  owner_id INTEGER NOT NULL REFERENCES owners(id), date TEXT NOT NULL,
  qty_in INTEGER NOT NULL, unit_cost REAL, reverse_pct REAL, note TEXT);
CREATE TABLE IF NOT EXISTS adjustments(
  id INTEGER PRIMARY KEY, lot_id INTEGER NOT NULL REFERENCES lots(id),
  date TEXT NOT NULL, delta INTEGER NOT NULL, reason TEXT);
CREATE TABLE IF NOT EXISTS sales(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, payment TEXT DEFAULT 'Espèces', note TEXT,
  user_name TEXT DEFAULT 'Anonyme', customer_gender TEXT, customer_age_group TEXT, is_star INTEGER DEFAULT 0, service_moment TEXT);
CREATE TABLE IF NOT EXISTS cash_movements(
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL,
  user_name TEXT NOT NULL,
  type TEXT NOT NULL,        -- 'DEPOSIT' (le libraire dépose l'argent dans la caisse), 'WITHDRAWAL' (retrait/remboursement par la caisse), 'ADJUST'
  channel TEXT NOT NULL,     -- 'ESPECES' | 'WERO' | 'PAYPAL'
  amount REAL NOT NULL,
  note TEXT);
CREATE TABLE IF NOT EXISTS sale_lines(
  id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
  book_id INTEGER NOT NULL REFERENCES books(id), qty INTEGER NOT NULL, unit_price REAL NOT NULL);
CREATE TABLE IF NOT EXISTS allocations(
  id INTEGER PRIMARY KEY, line_id INTEGER NOT NULL REFERENCES sale_lines(id) ON DELETE CASCADE,
  book_id INTEGER NOT NULL REFERENCES books(id), lot_id INTEGER REFERENCES lots(id),
  owner_id INTEGER REFERENCES owners(id), qty INTEGER NOT NULL,
  revenue REAL NOT NULL, due REAL NOT NULL DEFAULT 0, date TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settlements(
  id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES owners(id),
  date TEXT NOT NULL, amount REAL NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS reservations(
  id INTEGER PRIMARY KEY, name TEXT, phone TEXT, title TEXT, qty INTEGER DEFAULT 1,
  date TEXT, status TEXT DEFAULT 'En attente', note TEXT);
CREATE TABLE IF NOT EXISTS dropdown_options(
  id INTEGER PRIMARY KEY,
  group_key TEXT NOT NULL, -- 'category' | 'type' | 'payment' | 'publisher'
  label TEXT NOT NULL,
  UNIQUE(group_key, label));
CREATE TABLE IF NOT EXISTS app_settings(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit_logs(
  id INTEGER PRIMARY KEY,
  timestamp TEXT NOT NULL,
  user_name TEXT NOT NULL DEFAULT 'Anonyme',
  action TEXT NOT NULL,         -- 'INSERT' | 'UPDATE' | 'DELETE' | 'SALE' | 'ADJUST' ...
  target_type TEXT NOT NULL,    -- 'book' | 'lot' | 'sale' | 'reservation' | 'owner' | 'option' | 'adjustment' ...
  target_id INTEGER,
  summary TEXT NOT NULL,
  snapshot_before TEXT,         -- JSON
  snapshot_after TEXT,          -- JSON
  undone INTEGER NOT NULL DEFAULT 0,
  undone_at TEXT,
  undone_by TEXT);
CREATE TABLE IF NOT EXISTS sale_payments(
  id INTEGER PRIMARY KEY,
  sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
  payment TEXT NOT NULL,
  amount REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_alloc_date ON allocations(date);
CREATE INDEX IF NOT EXISTS ix_alloc_book ON allocations(book_id);
CREATE INDEX IF NOT EXISTS ix_lots_book ON lots(book_id);
CREATE INDEX IF NOT EXISTS ix_adjustments_lot ON adjustments(lot_id);
CREATE INDEX IF NOT EXISTS ix_books_active ON books(active);
CREATE INDEX IF NOT EXISTS ix_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS ix_sale_payments_sale ON sale_payments(sale_id);
"""


def connect():
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")       # Journalisation write-ahead : résistant aux crashs & arrêts brutaux
    c.execute("PRAGMA synchronous=NORMAL")      # Compromis standard industriel ultra-sûr en mode WAL
    c.execute("PRAGMA busy_timeout=15000")      # Évite tout blocage en cas d'accès simultané
    # Optimisations 32-bit & rush caisse :
    c.execute("PRAGMA cache_size=-8000")        # 8 Mo de cache mémoire pages (extrêmement rapide, 0 pression RAM)
    c.execute("PRAGMA temp_store=MEMORY")       # Tables et tris temporaires en RAM (évite I/O disque lent)
    c.execute("PRAGMA mmap_size=0")             # Évite la fragmentation d'espace d'adressage virtuel 2 Go en 32-bit
    return c


@contextmanager
def tx(immediate=False):
    """Gestionnaire de transaction résilient.
    immediate=True : acquiert un verrou d'écriture exclusif (BEGIN IMMEDIATE) pour éliminer les
    risques de collision ou d'interblocage lors des encaissements simultanés multi-terminaux."""
    c = connect()
    try:
        if immediate:
            c.execute("BEGIN IMMEDIATE")
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def clean_gdpr_reservations(c, days_retention=90):
    """RGPD Art. 5.1.e (Limitation de la conservation) & Art. 5.1.c (Minimisation) :
    Anonymise les coordonnées personnelles (téléphone, nom) des réservations
    terminées ('Servie' ou 'Annulée') datant de plus de `days_retention` jours."""
    cutoff = (date.today() - timedelta(days=days_retention)).isoformat()
    candidates = c.execute("""
        SELECT id, name, phone, date, status FROM reservations
        WHERE (status IN ('Servie', 'Annulée') OR date < ?)
        AND (phone IS NOT NULL OR name NOT LIKE 'Client RGPD-%')
    """, (cutoff,)).fetchall()
    count = 0
    for r in candidates:
        anonymized_name = f"Client RGPD #{r['id']}"
        c.execute("""
            UPDATE reservations
            SET name = ?, phone = NULL, note = COALESCE(note, '') || ' [Données personnelles anonymisées RGPD]'
            WHERE id = ?
        """, (anonymized_name, r["id"]))
        count += 1
    return count


def safe_backup_db(target_path):
    """Effectue une sauvegarde à chaud 100% cohérente et atomique via l'API sqlite3.backup()."""
    tmp_target = target_path + ".tmp"
    src = connect()
    try:
        dst = sqlite3.connect(tmp_target)
        try:
            with dst:
                src.backup(dst, pages=100)
        finally:
            dst.close()
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass
        os.replace(tmp_target, target_path)
    finally:
        src.close()


def backup_before_migration(source, database_name="librairie"):
    backup_dir = os.path.join(DATA_DIR, "sauvegardes")
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = os.path.join(backup_dir, f"{database_name}_pre_migration_{timestamp}.db")
    fd, temporary = tempfile.mkstemp(prefix=".migration-", suffix=".db", dir=backup_dir)
    os.close(fd)
    try:
        backup = sqlite3.connect(temporary)
        try:
            source.backup(backup)
            result = backup.execute("PRAGMA quick_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError(f"Database migration backup failed integrity check: {result}")
        finally:
            backup.close()
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def init():
    database_existed = os.path.isfile(DB_PATH) and os.path.getsize(DB_PATH) > 0
    current_version = 0
    if database_existed:
        source = connect()
        try:
            current_version = source.execute("PRAGMA user_version").fetchone()[0]
            if current_version > LATEST_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {current_version} is newer than this eLib build "
                    f"supports ({LATEST_SCHEMA_VERSION})."
                )
            if current_version < LATEST_SCHEMA_VERSION:
                backup_before_migration(source, "librairie")
        finally:
            source.close()

    with tx() as c:
        c.executescript(SCHEMA)
        # Migration dynamique pour tables existantes
        c.execute("""
            CREATE TABLE IF NOT EXISTS sale_payments(
              id INTEGER PRIMARY KEY,
              sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
              payment TEXT NOT NULL,
              amount REAL NOT NULL);
        """)
        c.execute("CREATE INDEX IF NOT EXISTS ix_sale_payments_sale ON sale_payments(sale_id);")
        # Rétrocompatibilité : initialiser sale_payments pour les ventes existantes
        c.execute("""
            INSERT INTO sale_payments(sale_id, payment, amount)
            SELECT s.id, COALESCE(s.payment, 'Espèces'), COALESCE(SUM(l.qty * l.unit_price), 0)
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            WHERE s.id NOT IN (SELECT sale_id FROM sale_payments)
            GROUP BY s.id, s.payment
        """)
        cols_sales = [r["name"] for r in rows(c, "PRAGMA table_info(sales)")]
        if "user_name" not in cols_sales:
            c.execute("ALTER TABLE sales ADD COLUMN user_name TEXT DEFAULT 'Anonyme'")
        if "customer_gender" not in cols_sales:
            c.execute("ALTER TABLE sales ADD COLUMN customer_gender TEXT")
        if "customer_age_group" not in cols_sales:
            c.execute("ALTER TABLE sales ADD COLUMN customer_age_group TEXT")
        if "is_star" not in cols_sales:
            c.execute("ALTER TABLE sales ADD COLUMN is_star INTEGER DEFAULT 0")
        if "service_moment" not in cols_sales:
            c.execute("ALTER TABLE sales ADD COLUMN service_moment TEXT")
        if not c.execute("SELECT 1 FROM owners").fetchone():
            c.execute("INSERT INTO owners(name,kind,reverse_pct,priority,color) VALUES('Cité Royale','maison_mere',100,1,'#ffb454')")
            c.execute("INSERT INTO owners(name,kind,reverse_pct,priority,color) VALUES('ICC Rennes','locale',0,2,'#5ee6b0')")
        
        # Initialisation des options de base si table vide
        if not c.execute("SELECT 1 FROM dropdown_options").fetchone():
            default_opts = [
                ('category', 'Standard'), ('category', 'Bible'), ('category', 'Pack'), ('category', 'Enfant'), ('category', 'Vie chrétienne'),
                ('type', 'Souple'), ('type', 'Rigide'), ('type', 'Poche'), ('type', 'Broché'),
                ('payment', 'Espèces'), ('payment', 'CB'), ('payment', 'Wero'), ('payment', 'Don / Offert'),
                ('service_moment', '1er Culte (Principal)'), ('service_moment', '2e Culte (Jeunes EJP)'), ('service_moment', 'Occasion spéciale'), ('service_moment', 'En semaine / Autre'),
                ('publisher', 'Metanoia & Vie'), ('publisher', 'Société Biblique de Genève'), ('publisher', 'Excelsis'), ('publisher', 'RADD')
            ]
            c.executemany("INSERT OR IGNORE INTO dropdown_options(group_key, label) VALUES(?,?)", default_opts)
        else:
            # Fusion de PayPal POS (CB) vers CB et maintien des options de base
            c.execute("INSERT OR IGNORE INTO dropdown_options(group_key, label) VALUES('payment', 'CB')")
            c.execute("DELETE FROM dropdown_options WHERE group_key='payment' AND (label='PayPal POS (CB)' OR label LIKE '%PayPal%')")
            c.execute("UPDATE sales SET payment='CB' WHERE payment='PayPal POS (CB)' OR payment LIKE '%PayPal%'")
            c.execute("INSERT OR IGNORE INTO dropdown_options(group_key, label) VALUES('payment', 'Wero')")
            # S'assurer des options de cultes par défaut
            for sm in ['1er Culte (Principal)', '2e Culte (Jeunes EJP)', 'Occasion spéciale', 'En semaine / Autre']:
                c.execute("INSERT OR IGNORE INTO dropdown_options(group_key, label) VALUES('service_moment', ?)", (sm,))

        # Initialisation d'un premier profil utilisateur si vide
        if not c.execute("SELECT 1 FROM users").fetchone():
            c.execute("INSERT OR IGNORE INTO users(name) VALUES('Responsable')")
        if current_version < 1:
            current_version = 1
        for target_version in range(max(2, current_version + 1), LATEST_SCHEMA_VERSION + 1):
            migration = SCHEMA_MIGRATIONS.get(target_version)
            if migration is None:
                raise RuntimeError(f"Missing database migration for schema version {target_version}.")
            migration(c)
            current_version = target_version
        c.execute(f"PRAGMA user_version={current_version}")


def rows(c, sql, args=()):
    return [dict(r) for r in c.execute(sql, args).fetchall()]


def get_setting(c, key, default=None):
    row = c.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def is_card_payment(payment):
    label = (payment or "").strip().lower()
    return any(token in label for token in ("cb", "paypal", "carte", "card", "visa", "mastercard", "credit", "debit"))


def owner_payable_due(c, owner_id, user_name=None):
    """Return the amount payable from the local till, based on recorded payment channels."""
    owner = c.execute("SELECT name FROM owners WHERE id=?", (owner_id,)).fetchone()
    if not owner:
        return 0

    user_filter = " AND s.user_name=?" if user_name is not None else ""
    args = (owner_id, user_name) if user_name is not None else (owner_id,)
    if owner["name"].strip().lower() != "cité royale":
        return c.execute(
            f"""SELECT COALESCE(SUM(a.due), 0)
                FROM allocations a
                JOIN sale_lines sl ON sl.id=a.line_id
                JOIN sales s ON s.id=sl.sale_id
                WHERE a.owner_id=?{user_filter}""",
            args,
        ).fetchone()[0]

    due_by_sale = {
        row["sale_id"]: row["due"]
        for row in c.execute(
            f"""SELECT sl.sale_id, COALESCE(SUM(a.due), 0) due
                FROM allocations a
                JOIN sale_lines sl ON sl.id=a.line_id
                JOIN sales s ON s.id=sl.sale_id
                WHERE a.owner_id=?{user_filter}
                GROUP BY sl.sale_id""",
            args,
        ).fetchall()
    }
    if not due_by_sale:
        return 0
    sale_ids = list(due_by_sale)
    placeholders = ",".join("?" for _ in sale_ids)
    sale_totals = {
        row["sale_id"]: row["total"]
        for row in c.execute(
            f"""SELECT sale_id, COALESCE(SUM(qty * unit_price), 0) total
                FROM sale_lines WHERE sale_id IN ({placeholders}) GROUP BY sale_id""",
            sale_ids,
        ).fetchall()
    }
    payment_args = (user_name,) if user_name is not None else ()
    payment_user_filter = " AND s.user_name=?" if user_name is not None else ""
    non_card_by_sale = {}
    for row in c.execute(
        f"""SELECT sp.sale_id, sp.payment, sp.amount
            FROM sale_payments sp
            JOIN sales s ON s.id=sp.sale_id
            WHERE 1=1{payment_user_filter}""",
        payment_args,
    ).fetchall():
        if not is_card_payment(row["payment"]):
            non_card_by_sale[row["sale_id"]] = non_card_by_sale.get(row["sale_id"], 0) + row["amount"]
    return sum(
        min(
            due,
            non_card_by_sale.get(sale_id, 0)
            * min(1, due / sale_totals[sale_id])
            if sale_totals.get(sale_id, 0) > 0
            else 0,
        )
        for sale_id, due in due_by_sale.items()
    )


def log_audit(c, user_name, action, target_type, target_id, summary, snapshot_before=None, snapshot_after=None):
    """Enregistre une opération atomique avec instantané avant/après (JSON) pour traçabilité et annulation."""
    import json
    ts = datetime.now().isoformat(timespec='seconds')
    sb = json.dumps(snapshot_before, ensure_ascii=False) if snapshot_before is not None else None
    sa = json.dumps(snapshot_after, ensure_ascii=False) if snapshot_after is not None else None
    cur = c.execute("""INSERT INTO audit_logs(timestamp, user_name, action, target_type, target_id, summary, snapshot_before, snapshot_after)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (ts, user_name or 'Anonyme', action, target_type, target_id, summary, sb, sa))
    return cur.lastrowid


LOT_REMAINING = """
 l.qty_in - COALESCE((SELECT SUM(a.qty) FROM allocations a WHERE a.lot_id=l.id),0)
          + COALESCE((SELECT SUM(j.delta) FROM adjustments j WHERE j.lot_id=l.id),0)"""


def book_stock(c, book_id):
    r = c.execute(f"SELECT COALESCE(SUM({LOT_REMAINING}),0) s FROM lots l WHERE l.book_id=?", (book_id,)).fetchone()
    return r["s"]


def pack_stock(c, pack_id):
    items = rows(c, "SELECT book_id, qty FROM pack_items WHERE pack_id=?", (pack_id,))
    if not items:
        return 0
    return max(0, min(book_stock(c, i["book_id"]) // max(1, i["qty"]) for i in items))


def _due_per_unit(lot, owner, price):
    if lot is None:
        return 0.0
    if lot["unit_cost"] is not None:
        return float(lot["unit_cost"])
    pct = lot["reverse_pct"] if lot["reverse_pct"] is not None else owner["reverse_pct"]
    return price * float(pct) / 100.0


def _allocate_book(c, line_id, book_id, qty, unit_revenue, day):
    """Consomme les lots selon la priorité (propriétaire.priority puis FIFO)."""
    lots = rows(c, f"""SELECT l.*, o.reverse_pct o_pct, o.priority, ({LOT_REMAINING}) remaining
        FROM lots l JOIN owners o ON o.id=l.owner_id WHERE l.book_id=?
        ORDER BY o.priority, l.date, l.id""", (book_id,))
    left = qty
    owners = {o["id"]: o for o in rows(c, "SELECT * FROM owners")}
    for l in lots:
        if left <= 0:
            break
        if l["remaining"] <= 0:
            continue
        take = min(left, l["remaining"])
        owner = owners[l["owner_id"]]
        due = _due_per_unit(l, owner, unit_revenue) * take
        c.execute("INSERT INTO allocations(line_id,book_id,lot_id,owner_id,qty,revenue,due,date) VALUES(?,?,?,?,?,?,?,?)",
                  (line_id, book_id, l["id"], l["owner_id"], take, unit_revenue * take, due, day))
        left -= take
    if left > 0:  # vente sans stock suffisant : tracée, sans propriétaire
        c.execute("INSERT INTO allocations(line_id,book_id,lot_id,owner_id,qty,revenue,due,date) VALUES(?,?,NULL,NULL,?,?,0,?)",
                  (line_id, book_id, left, unit_revenue * left, day))
    return left


def _insert_alloc(c, line_id, book_id, lot_id, qty, unit_rev, day):
    """Impute `qty` exemplaires à un lot choisi par le libraire (ventes hors stock strictement interdites)."""
    if qty <= 0:
        raise ValueError("Quantité invalide")
    if lot_id is None:
        bk = c.execute("SELECT title FROM books WHERE id=?", (book_id,)).fetchone()
        title = bk["title"] if bk else f"Livre #{book_id}"
        raise ValueError(f"Vente hors stock interdite pour « {title} » : chaque exemplaire doit être alloué à un lot existant en stock.")
    lot = c.execute(f"SELECT l.*, ({LOT_REMAINING}) remaining FROM lots l WHERE l.id=?", (lot_id,)).fetchone()
    if not lot or lot["book_id"] != book_id:
        raise ValueError("Lot incohérent avec le livre")
    if lot["remaining"] < qty:
        bk = c.execute("SELECT title FROM books WHERE id=?", (book_id,)).fetchone()
        title = bk["title"] if bk else f"Livre #{book_id}"
        raise ValueError(f"Stock insuffisant pour « {title} » : le lot choisi n'a que {lot['remaining']} exemplaire(s) disponible(s)")
    owner = c.execute("SELECT * FROM owners WHERE id=?", (lot["owner_id"],)).fetchone()
    due = _due_per_unit(lot, owner, unit_rev) * qty
    c.execute("INSERT INTO allocations(line_id,book_id,lot_id,owner_id,qty,revenue,due,date) VALUES(?,?,?,?,?,?,?,?)",
              (line_id, book_id, lot_id, lot["owner_id"], qty, unit_rev * qty, due, day))


def create_sale(c, day, payment, note, lines, manual=True, user_name="Anonyme", customer_gender=None, customer_age_group=None, is_star=0, service_moment=None, payments=None):
    """lines: [{book_id, qty, unit_price, allocations:[{book_id, lot_id, qty}]}] -> (sale_id, warnings).
    manual=True : le libraire désigne explicitement les lots (aucun choix automatique).
    manual=False : réservé à l'import de l'historique Excel (répartition auto, priorité des origines).
    payments: facultatif, liste de dicts [{payment: str, amount: float}] pour multi-paiements."""
    day = day or date.today().isoformat()
    if not lines:
        raise ValueError("Panier vide")
    warnings = []

    if payments and len(payments) > 0:
        pay_summary = " + ".join([f"{float(p['amount']):.2f} € {p['payment']}" for p in payments])
        eff_payment = payment if (payment and payment != "Espèces" and payment != pay_summary) else pay_summary
    else:
        eff_payment = payment or "Espèces"

    sale_id = c.execute("INSERT INTO sales(date,payment,note,user_name,customer_gender,customer_age_group,is_star,service_moment) VALUES(?,?,?,?,?,?,?,?)",
                        (day, eff_payment, note, user_name or "Anonyme", customer_gender, customer_age_group, int(bool(is_star)), service_moment)).lastrowid

    tot_sale = 0.0
    for ln in lines:
        b = c.execute("SELECT * FROM books WHERE id=?", (ln["book_id"],)).fetchone()
        qty = int(ln["qty"])
        price = float(ln["unit_price"] if ln.get("unit_price") is not None else b["price"])
        tot_sale += qty * price
        lid = c.execute("INSERT INTO sale_lines(sale_id,book_id,qty,unit_price) VALUES(?,?,?,?)",
                        (sale_id, b["id"], qty, price)).lastrowid
        if b["is_pack"]:
            items = rows(c, """SELECT pi.book_id, pi.qty, bk.price, bk.title FROM pack_items pi
                JOIN books bk ON bk.id=pi.book_id WHERE pi.pack_id=?""", (b["id"],))
            if not items:
                raise ValueError(f"Pack vide : {b['title']}")
            tot = sum((i["price"] or 0) * i["qty"] for i in items)
            comps = [(i["book_id"], qty * i["qty"],
                      price * (((i["price"] or 0) * i["qty"] / tot) if tot > 0 else 1.0 / len(items)) / i["qty"], i["title"])
                     for i in items]
        else:
            comps = [(b["id"], qty, price, b["title"])]
        for book_id, need, unit_rev, title in comps:
            if not manual:
                short = _allocate_book(c, lid, book_id, need, unit_rev, day)
                if short:
                    warnings.append(f"{short} exemplaire(s) sans stock : {title}")
                continue
            al = [a for a in (ln.get("allocations") or []) if int(a.get("book_id") or b["id"]) == book_id and int(a["qty"]) > 0]
            if sum(int(a["qty"]) for a in al) != need:
                raise ValueError(f"Choisissez le lot de chaque exemplaire : « {title} » ({need} à répartir)")
            for a in al:
                _insert_alloc(c, lid, book_id, a.get("lot_id"), int(a["qty"]), unit_rev, day)

    # Enregistrement des paiements (détaillés ou unique)
    if payments and len(payments) > 0:
        for p in payments:
            c.execute("INSERT INTO sale_payments(sale_id,payment,amount) VALUES(?,?,?)",
                      (sale_id, p["payment"], float(p["amount"])))
    else:
        c.execute("INSERT INTO sale_payments(sale_id,payment,amount) VALUES(?,?,?)",
                  (sale_id, eff_payment, tot_sale))

    return sale_id, warnings
