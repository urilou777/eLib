# eLib – Gestion de stock, ventes & statistiques

Application locale (100% hors-ligne) pour la gestion d'une librairie, avec synchronisation continue vers Excel et base de données SQLite.

Dépôt GitHub : [https://github.com/urilou777/eLib](https://github.com/urilou777/eLib)

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

## ⛪ Procédure de Déploiement à l'Église (Pas à Pas)

Ce guide détaille la mise en service complète de la librairie le jour du culte, que vous utilisiez ce PC portable ou un autre PC à l'église.

---

### 📋 Checklist Rapide avant le Culte

- [ ] **Code à jour** : Dépôt GitHub cloné ou `git pull` effectué.
- [ ] **Base de données transférée** (si changement de PC) : Le fichier `data/librairie.db` contient tous les livres, stocks et ventes. **Attention : ce dossier est dans `.gitignore` (zéro cloud). Si vous changez de PC, copiez impérativement le dossier `data/` sur clé USB !**
- [ ] **Réseau Wi-Fi commun** : Le PC de caisse et les smartphones des bénévoles doivent être connectés au **même réseau** (Wi-Fi de l'église ou Partage de connexion 4G/5G).
- [ ] **Profil Réseau Windows en "Privé"** : Ne laissez pas Windows en "Réseau Public", sinon le pare-feu bloque l'accès des téléphones.

---

### 🖥️ Étape 1 : Préparation du PC de Caisse (Windows 32-bit ou 64-bit)

Deux options au choix selon le PC de l'église :

#### Option A : Clé USB 100% Autonome "Zero-Install" (Recommandé pour Windows 32-bit & 64-bit)
Aucune installation de Python ni droits administrateur requis sur le PC hôte :
1. Le dossier `runtime_win32/` contient un environnement Python 32-bit portable complet préconfiguré.
2. Copiez simplement l'intégralité du dossier `librairie` sur votre clé USB (avec `runtime_win32/` et votre dossier `data/`).
3. Branchez la clé sur le PC de l'église et double-cliquez directement sur **`Lancer_Librairie.bat`** (ou utilisez **`dist/Librairie.exe`**). Le lanceur détecte automatiquement le moteur 32-bit embarqué !

#### Option B : Installation classique avec Python
- **Si le PC est en Windows 10 32-bit** : Téléchargez impérativement l'installateur **32-bit (x86)** :
  👉 [Télécharger Python 3.13.2 (32-bit / x86)](https://www.python.org/ftp/python/3.13.2/python-3.13.2.exe)
  *(Ne cliquez pas sur le bouton jaune par défaut sur python.org car il télécharge la version 64-bit incompatible !)*
- **Si le PC est en Windows 64-bit** : Téléchargez Python 3.13+ 64-bit standard.
- **IMPORTANT** : Cochez impérativement la case **☑ Add python.exe to PATH** en bas lors de l'installation !

Puis dans PowerShell / Invite de commandes :
```powershell
pip install -r requirements.txt
```

#### 3. Transférer la base de données réelle (si nouveau PC)
Si vous installez le projet sur un autre ordinateur que celui-ci :
1. Sur votre PC actuel, copiez le dossier `data/` (qui contient `librairie.db` et vos sauvegardes).
2. Collez-le à la racine du projet sur le nouveau PC : `chemin/vers/librairie/data/librairie.db`.

---

### 📱 Étape 2 : Configuration du Réseau & Scanner Mobile (1 seule fois par lieu)

Pour permettre aux bénévoles d'utiliser l'appareil photo de leur smartphone comme douchette :

#### 1. Régler le réseau Windows en "Réseau Privé"
1. Connectez le PC au Wi-Fi de l'église (ou au partage de connexion 4G).
2. Ouvrez les **Paramètres Windows** > **Réseau et Internet** > **Wi-Fi** (ou Ethernet) > Cliquez sur le nom de votre réseau.
3. Cochez **Type de profil réseau : Réseau privé** (indispensable pour que Windows autorise les smartphones à joindre le port HTTPS).

#### 2. Configurer les Certificats & Pare-feu
Faites un **clic droit sur `Installer_Mobile.bat`** > **Exécuter en tant qu'administrateur**.
Ce script automatique :
- Détecte l'adresse IP locale du PC sur le réseau de l'église.
- Génère les certificats TLS sécurisés (HTTPS) nécessaires pour activer la caméra sur Android/iOS.
- Ouvre le port TCP 8766 dans le pare-feu Windows pour le sous-réseau local.

---

### 🚀 Étape 3 : Lancement de la Caisse

Double-cliquez simplement sur :
```text
Lancer_Librairie.bat
```
*(Ou en ligne de commande : `python run.py`)*

1. L'application démarre le serveur local et s'ouvre dans une fenêtre dédiée (ou votre navigateur sur `http://127.0.0.1:8765`).
2. L'écoute HTTPS locale pour les smartphones est active automatiquement sur le port 8766.

---

### 📲 Étape 4 : Connexion des Smartphones des Bénévoles

1. Sur le PC de caisse, rendez-vous dans l'onglet **Caisse**.
2. Cliquez sur le bouton bleu **📱 Ouvrir Scanner Mobile** : le QR code d'appairage s'affiche à l'écran.
3. Chaque bénévole ouvre l'appareil photo de son smartphone (connecté au même Wi-Fi) et scanne le QR code.
4. Le smartphone ouvre l'URL sécurisée `https://<IP_PC>:8766/mobile#token=...` :
   - *Premier accès* : Le navigateur du smartphone affiche un avertissement de sécurité standard (certificat local privé). Cliquez sur **Paramètres avancés** puis **Continuer vers le site (non sécurisé)**.
   - Vous pouvez également installer le certificat racine CA en 1 clic via le lien proposé pour supprimer tout avertissement.
5. L'interface mobile démarre instantanément :
   - Choisissez le nom du libraire bénévole dans la liste.
   - Visez les codes-barres des livres : détection immédiate, bips sonores, et panier synchronisé en temps réel sur la Régie du PC !

---

### ✂️ Outil Annexe : Atelier de Scission des Ventes Historiques

Si vous souhaitez scinder les 14 tickets groupés historiques ou renseigner des codes-barres manquants :
Double-cliquez sur :
```text
Lancer_Atelier_Scission.bat
```
L'interface d'atelier dédiée s'ouvre sur `http://127.0.0.1:8769` avec les 14 ventes historiques filtrées et prêtes à être ventilées en paniers distincts sans toucher au stock.

---

### 🆘 En cas d'imprévu le jour J (Plan B)

* **Le Wi-Fi de l'église bloque les connexions directes entre appareils (isolation client) :**
  Activez le **Partage de connexion 4G/5G** sur l'un de vos smartphones. Connectez le PC et les autres téléphones sur ce partage de connexion. Lancez `Installer_Mobile.bat` pour prendre en compte la nouvelle IP, et démarrez `Lancer_Librairie.bat`.
* **Coupure de courant inopinée :**
  La base SQLite tourne en mode **WAL (Write-Ahead Logging)** : aucune vente n'est corrompue ou perdue. Rallumez simplement le PC et relancez `Lancer_Librairie.bat`.
* **Archivage fin de service :**
  À la fin des cultes, allez dans l'onglet **Données & Excel** > Cliquez sur **💾 Sauvegarde immédiate** ou téléchargez le classeur Excel miroir pour vos archives.

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
- `Lancer_Librairie.bat` : Lanceur double-clic pour la caisse principale.
- `Lancer_Atelier_Scission.bat` : Lanceur de l'atelier de scission et gestion des codes-barres.
- `requirements.txt` : Dépendances Python (FastAPI, Uvicorn, Pillow, OpenPyXL, etc.).

