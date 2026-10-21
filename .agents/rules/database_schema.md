# Règle Métier : Schéma de Données & Invariants SQLite

Avant toute modification de la base de données, ajout d'endpoint ou modification de la logique d'encaissement et de stock, consulter le schéma de référence complet :
👉 [SCHEMA.md](../../SCHEMA.md) (à la racine du dépôt)

### Invariants Clés :
1. **Traçabilité des Lots** : Tout exemplaire vendu (`sale_lines`) doit être alloué (`allocations`) à un lot réel (`lots`).
2. **Reversements & Origines** :
   - `Cité Royale` : `reverse_pct = 100` (montant total reversé en fin de période).
   - `ICC Rennes` : `reverse_pct = 0` (marge 100% conservée par la librairie locale).
3. **Multi-paiements** : Tout encaissement fractionné est enregistré dans `sale_payments` avec la clé étrangère `sale_id REFERENCES sales(id) ON DELETE CASCADE`.
4. **Audit** : Toute mutation de stock ou de vente est loggée dans `audit_logs` avec snapshot JSON.
