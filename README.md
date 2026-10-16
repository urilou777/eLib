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

6. **Résilience Maximale & Anti-Corruption (Zero Cloud, Anti-Crash)** :
   - **Mode SQLite WAL (Write-Ahead Logging)** : protège la base contre les coupures brutales de courant, fermetures inopinées du logiciel ou accès simultanés.
   - **Sauvegardes à chaud non bloquantes (`sqlite3.backup()`)** : snapshots complets et cohérents en mémoire sans verrouiller la base.
   - **Écritures atomiques avec fichiers temporaires (`.tmp`) et permutation atomique (`os.replace`)** : aucun risque d'avoir un fichier tronqué ou corrompu sur disque en cas d'interruption.
   - **Gestionnaire visuel de sauvegardes** (dans *Données & Excel*) :
     - Liste de tous les snapshots de base (`.db`) et classeurs Excel (`.xlsx`).
     - **Téléchargement** direct d'un clic pour archivage sur clé USB ou disque externe.
     - **Restauration immédiate (`↺ Restaurer`)** d'un point antérieur (avec création automatique d'une copie de précaution avant restauration).
     - **Journal d'Audit & Undo** : traçabilité de chaque action par utilisateur et retour arrière direct sur chaque opération unitaire.

6. **Scanner Mobile pour Libraires (Multi-encaissement autonome sur smartphone)** :
   - Chaque libraire peut utiliser l'appareil photo de son smartphone comme douchette code-barres et encaisser en direct.
   - **Architecture TLS Locale & Privée (100% hors-ligne)** : Autorité racine locale dédiée (CA EC P-256) avec génération automatique de certificats serveurs pour les adresses IP du réseau local.
   - **Sécurité et Permissions Android/iOS** : Conforme aux exigences strictes des contextes sécurisés HTTPS (`getUserMedia`), headers de sécurité stricts (CSP, Permissions-Policy restreignant la caméra à l'origine locale), et appairage cryptographique par token unique (zéro mot de passe à taper).
   - **Isolation réseau & Pare-feu** : L'accès LAN est strictement cloisonné aux opérations de caisse mobile autorisées. Les opérations sensibles (restaurations de base, gestion des sauvegardes, imports/exports) restent rigoureusement confinées au poste central (`127.0.0.1`).

---

## 🛠️ Installation & Démarrage

### Option 1 : Lancement rapide via script Windows (recommandé)
Double-cliquez simplement sur :
```text
Lancer_Librairie.bat
```
L'application démarre le serveur local et s'ouvre dans une fenêtre dédiée (ou votre navigateur à l'adresse `http://127.0.0.1:8765`).

### Configuration du Scanner Mobile (Une seule fois)
Pour activer les téléphones en Wi-Fi local :
1. Lancez **`Installer_Mobile.bat`** (clic droit > *Exécuter en tant qu'administrateur*). Ce script :
   - Détecte l'IP locale du PC et génère les certificats TLS requis.
   - Configure automatiquement la règle de pare-feu Windows pour le port HTTPS (8766), restreinte au profil privé et au sous-réseau local.
2. Démarrez l'application, ouvrez l'onglet **Caisse**, puis cliquez sur **📱 Ouvrir Scanner Mobile** pour afficher le QR code d'appairage.

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
  - `db.py` : Schéma SQLite, gestion atomique des lots, packs, trésorerie et transactions.
  - `certs.py` : PKI locale automatisée (CA racine, certificats serveurs dynamiques).
  - `security.py` : Middleware de contrôle d'accès réseau, anti-spoofing Host, rate-limiting et gestion des tokens smartphones.
  - `excel_io.py` : Moteur d'importation et d'exportation Excel.
  - `main.py` : API FastAPI locale et sécurisée, boucle d'archivage miroir en arrière-plan.
  - `static/` : Interface web moderne desktop et mobile (HTML5, Vanilla CSS, Vanilla JS, librairie ZXing embarquée hors-ligne).
- `setup_mobile.py` & `Installer_Mobile.bat` : Outil de configuration automatique des certificats et du pare-feu.
- `run.py` : Point d'entrée avec double liaison réseau (HTTP 127.0.0.1 + HTTPS LAN sécurisé).
- `Lancer_Librairie.bat` : Lanceur double-clic pour Windows.
- `requirements.txt` : Dépendances Python.

