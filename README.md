# Librairie – Gestion de stock, ventes & statistiques

Application locale (100% hors-ligne) pour la gestion d'une librairie, avec synchronisation continue vers Excel et base de données SQLite.

Dépôt GitHub : [https://github.com/urilou777/librairi-e](https://github.com/urilou777/librairi-e)

---

## 🚀 Fonctionnalités principales

1. **Tableau de bord dynamique & Visualisations** :
   - Évolution mensuelle du Chiffre d'Affaires par origine (Maison mère vs Église locale).
   - Courbes de tendances (moyenne mobile) et prévisions automatisées sur 3 mois.
   - Graphique circulaire (donut) de répartition des ventes par provenance.
   - Top 10 des ventes, répartition par catégorie, éditeur, panier moyen, et jours de la semaine.
   - Alertes de stock bas en temps réel avec estimation d'autonomie en jours.

2. **Caisse & Vente au comptoir (Drag & Drop)** :
   - Recherche instantanée par titre, auteur, éditeur ou scan de code-barres ISBN.
   - Ajout d'articles au panier par glisser-déposer ou clic direct.
   - **Contrôle manuel et atomique des stocks** : pour chaque exemplaire vendu, le libraire choisit explicitement le lot et l'origine (Cité Royale, ICC Rennes, etc.). Aucun arbitrage automatique opaque.
   - Prise en charge des packs/bundles avec décomposition et imputation unitaire de chaque livre.

3. **Multi-origines & Reversements** :
   - Gestion des stocks en dépôt (ex. Maison mère Cité Royale) et des stocks acquis (Église locale ICC Rennes).
   - Suivi en temps réel des montants dus à la maison mère et de la marge conservée par la librairie locale.
   - Enregistrement des règlements partiels ou totaux avec historique d'écritures.

4. **Catalogue & Packs** :
   - Fiches livres complètes (ISBN, titre, série, volume, auteur, éditeur, prix, seuil d'alerte).
   - Création et composition visuelle de packs par glisser-déposer de livres existants.

5. **Réservations / Commandes clients** :
   - Suivi des demandes spécifiques avec nom, téléphone et statut (En attente / Servie).

6. **Infrastructure Excel & SQLite (Zero Cloud)** :
   - **Base SQLite locale** (`data/librairie.db`), consultable à tout moment avec **LibreOffice Base** ou DB Browser for SQLite.
   - **Fichier Excel miroir automatique** (`data/Bibliotheque_miroir.xlsx`) recalculé et mis à jour après chaque transaction.
   - **Sauvegardes quotidiennes** horodatées (`data/sauvegardes/`) de la base et du classeur Excel.
   - Import/Export complet compatible avec la structure du fichier Excel d'origine.

---

## 🛠️ Installation & Démarrage

### Option 1 : Lancement rapide via script Windows (recommandé)
Double-cliquez simplement sur :
```text
Lancer_Librairie.bat
```
L'application démarre le serveur local et s'ouvre dans une fenêtre dédiée (ou votre navigateur à l'adresse `http://127.0.0.1:8765`).

### Option 2 : Exécutable autonome Windows (.exe)
Un exécutable portable autonome est disponible dans le dossier `dist/` :
```text
dist/Librairie.exe
```

### Option 3 : Lancement via ligne de commande
```powershell
pip install -r requirements.txt
python run.py
```

---

## 📁 Structure du projet

- `app/` :
  - `db.py` : Schéma SQLite, gestion atomique des lots, packs et transactions.
  - `excel_io.py` : Moteur d'importation et d'exportation Excel.
  - `main.py` : API locale FastAPI, boucle d'archivage miroir en arrière-plan.
  - `static/` : Interface web moderne (HTML5, Vanilla CSS avec design sombre & glassmorphism, Vanilla JS).
- `run.py` : Point d'entrée avec serveur local et encapsulation fenêtre native.
- `Lancer_Librairie.bat` : Lanceur double-clic pour Windows.
- `requirements.txt` : Dépendances Python (FastAPI, Uvicorn, openpyxl, pywebview, PyInstaller).
