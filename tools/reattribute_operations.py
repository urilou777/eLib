"""
Script sécurisé pour réattribuer toutes les opérations effectuées par d'autres comptes à "Uriel",
tout en préservant scrupuleusement l'intégrité de toutes les autres données.
"""
import sqlite3
import json
import shutil
import os
from datetime import datetime

DB_PATH = os.path.abspath("data/librairie.db")
DIST_DB_PATH = os.path.abspath("dist/data/librairie.db")
BACKUP_DIR = os.path.abspath("data/sauvegardes")
os.makedirs(BACKUP_DIR, exist_ok=True)

def main():
    print(f"Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # 1. État avant modification
    print("--- ÉTAT ACTUEL DES VENTES ---")
    sales_users = conn.execute("SELECT user_name, COUNT(*) as cnt FROM sales GROUP BY user_name").fetchall()
    for row in sales_users:
        print(f"  user_name: '{row['user_name']}' -> {row['cnt']} ventes")
    
    total_sales_count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    total_sales_amount = conn.execute("SELECT SUM(qty * unit_price) FROM sale_lines").fetchone()[0]
    total_lines_count = conn.execute("SELECT COUNT(*) FROM sale_lines").fetchone()[0]
    total_allocations_count = conn.execute("SELECT COUNT(*) FROM allocations").fetchone()[0]
    
    print(f"Total ventes: {total_sales_count}")
    print(f"Total lignes de vente: {total_lines_count}")
    print(f"Total montant ventes: {total_sales_amount}")
    print(f"Total allocations: {total_allocations_count}")
    
    print("\n--- ÉTAT ACTUEL DES MOUVEMENTS DE CAISSE ---")
    cash_users = conn.execute("SELECT user_name, COUNT(*) as cnt FROM cash_movements GROUP BY user_name").fetchall()
    if cash_users:
        for row in cash_users:
            print(f"  user_name: '{row['user_name']}' -> {row['cnt']} mouvements")
    else:
        print("  Aucun mouvement de caisse enregistré.")
        
    print("\n--- ÉTAT ACTUEL DES AUDIT LOGS ---")
    audit_users = conn.execute("SELECT user_name, COUNT(*) as cnt FROM audit_logs GROUP BY user_name").fetchall()
    for row in audit_users:
        print(f"  user_name: '{row['user_name']}' -> {row['cnt']} logs")
        
    # Check other tables for columns containing 'user'
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"\nTables trouvées dans la base : {tables}")
    for t in tables:
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        user_cols = [c for c in cols if 'user' in c.lower()]
        if user_cols:
            print(f"  Table '{t}' -> colonnes utilisateur: {user_cols}")

    # 2. Sauvegarde complète avant mutation
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"avant_reattribution_uriel_{timestamp}.db")
    print(f"\nCréation de la sauvegarde de sécurité : {backup_file}")
    
    # SQLite online backup to ensure clean snapshot even with WAL
    backup_conn = sqlite3.connect(backup_file)
    conn.backup(backup_conn)
    backup_conn.close()
    print("Sauvegarde de sécurité créée avec succès.")

    # 3. Réattribution des ventes à "Uriel"
    print("\nRéattribution de toutes les ventes à 'Uriel'...")
    cur = conn.execute("UPDATE sales SET user_name = 'Uriel' WHERE user_name != 'Uriel' OR user_name IS NULL")
    updated_sales = cur.rowcount
    print(f"  -> {updated_sales} ventes réattribuées à 'Uriel'.")

    # 4. Réattribution des mouvements de caisse à "Uriel"
    print("\nRéattribution des mouvements de caisse à 'Uriel'...")
    cur = conn.execute("UPDATE cash_movements SET user_name = 'Uriel' WHERE user_name != 'Uriel' OR user_name IS NULL")
    updated_cash = cur.rowcount
    print(f"  -> {updated_cash} mouvements réattribués à 'Uriel'.")

    # 5. Réattribution des logs d'audit et de leurs snapshots
    print("\nRéattribution des logs d'audit à 'Uriel'...")
    cur = conn.execute("UPDATE audit_logs SET user_name = 'Uriel' WHERE user_name != 'Uriel'")
    updated_audit = cur.rowcount
    print(f"  -> {updated_audit} logs d'audit réattribués à 'Uriel'.")
    
    # Update undone_by if any
    cur = conn.execute("UPDATE audit_logs SET undone_by = 'Uriel' WHERE undone_by IS NOT NULL AND undone_by != 'Uriel'")
    print(f"  -> {cur.rowcount} logs (champ undone_by) réattribués.")
    
    # Update snapshots in audit_logs
    print("\nMise à jour des instantanés JSON dans audit_logs...")
    logs_with_snapshots = conn.execute("SELECT id, snapshot_before, snapshot_after FROM audit_logs WHERE snapshot_before IS NOT NULL OR snapshot_after IS NOT NULL").fetchall()
    updated_snapshots_count = 0
    for row in logs_with_snapshots:
        lid = row["id"]
        sb = row["snapshot_before"]
        sa = row["snapshot_after"]
        changed = False
        
        if sb:
            try:
                data = json.loads(sb)
                if isinstance(data, dict):
                    if "user_name" in data and data["user_name"] != "Uriel":
                        data["user_name"] = "Uriel"
                        sb = json.dumps(data, ensure_ascii=False)
                        changed = True
                    if "user" in data and data["user"] != "Uriel":
                        data["user"] = "Uriel"
                        sb = json.dumps(data, ensure_ascii=False)
                        changed = True
            except Exception:
                pass
                
        if sa:
            try:
                data = json.loads(sa)
                if isinstance(data, dict):
                    if "user_name" in data and data["user_name"] != "Uriel":
                        data["user_name"] = "Uriel"
                        sa = json.dumps(data, ensure_ascii=False)
                        changed = True
                    if "user" in data and data["user"] != "Uriel":
                        data["user"] = "Uriel"
                        sa = json.dumps(data, ensure_ascii=False)
                        changed = True
            except Exception:
                pass
                
        if changed:
            conn.execute("UPDATE audit_logs SET snapshot_before = ?, snapshot_after = ? WHERE id = ?", (sb, sa, lid))
            updated_snapshots_count += 1
            
    print(f"  -> {updated_snapshots_count} snapshots JSON mis à jour.")

    # Validation et commit
    conn.commit()
    print("\nCommit terminé.")

    # 6. Vérifications strictes d'intégrité
    print("\n--- VÉRIFICATIONS D'INTÉGRITÉ APRÈS MUTATION ---")
    new_users = conn.execute("SELECT DISTINCT user_name FROM sales").fetchall()
    print(f"Utilisateurs distincts dans sales: {[r[0] for r in new_users]}")
    assert len(new_users) == 1 and new_users[0][0] == "Uriel", "Erreur: Toutes les ventes ne sont pas attribuées à Uriel !"

    new_sales_count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    new_sales_amount = conn.execute("SELECT SUM(qty * unit_price) FROM sale_lines").fetchone()[0]
    new_lines_count = conn.execute("SELECT COUNT(*) FROM sale_lines").fetchone()[0]
    new_allocations_count = conn.execute("SELECT COUNT(*) FROM allocations").fetchone()[0]

    print(f"Total ventes: {new_sales_count} (attendu: {total_sales_count})")
    print(f"Total lignes: {new_lines_count} (attendu: {total_lines_count})")
    print(f"Montant total: {new_sales_amount} (attendu: {total_sales_amount})")
    print(f"Total allocations: {new_allocations_count} (attendu: {total_allocations_count})")

    assert new_sales_count == total_sales_count, "Erreur: Le nombre de ventes a changé !"
    assert new_lines_count == total_lines_count, "Erreur: Le nombre de lignes a changé !"
    assert new_sales_amount == total_sales_amount, "Erreur: Le montant des ventes a changé !"
    assert new_allocations_count == total_allocations_count, "Erreur: Le nombre d'allocations a changé !"

    conn.close()
    print("\nIntégrité validée à 100% !")

    # 7. Synchronisation avec dist/data/librairie.db si présent
    if os.path.exists(DIST_DB_PATH):
        print(f"\nCopie de la base mise à jour vers {DIST_DB_PATH}...")
        shutil.copy2(DB_PATH, DIST_DB_PATH)
        print("dist/data/librairie.db synchronisé avec succès.")

    # 8. Rafraîchissement du miroir Excel
    try:
        from app import excel_io
        miroir_path = os.path.join(BACKUP_DIR, "Bibliotheque_miroir.xlsx")
        miroir_root = os.path.abspath("data/Bibliotheque_miroir.xlsx")
        print(f"\nExport du classeur miroir Excel actualisé...")
        excel_io.export_workbook(miroir_root)
        excel_io.export_workbook(miroir_path)
        print(f"Fichiers Excel exportés avec succès : {miroir_root} et {miroir_path}")
    except Exception as e:
        print(f"Note export Excel: {e}")

    print("\nOpération de réattribution à Uriel terminée avec succès !")

if __name__ == "__main__":
    main()
