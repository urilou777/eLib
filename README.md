# eLib – Gestion de stock, ventes & statistiques

Application locale (100% hors-ligne) pour la gestion d'une librairie, avec synchronisation continue vers Excel et base de données SQLite.

Dépôt GitHub : [https://github.com/urilou777/eLib](https://github.com/urilou777/eLib)

## Documentation technique

Les pages ci-dessous sont aussi disponibles hors ligne dans le dossier `docs\help\` :

- [Accueil de l’aide technique](docs/help/index.html)
- [Architecture et parcours des données](docs/help/architecture.html)
- [Scanner mobile et sécurité réseau](docs/help/mobile.html)
- [Données, sauvegardes et restauration](docs/help/data.html)
- [Application portable et compilation Windows](docs/help/build.html)
- [Code, tests et maintenance](docs/help/maintenance.html)
- [Sources et génération du fichier CHM](docs/help/eLib.hhp)

---

## 🚀 Fonctionnalités principales

Pour une présentation technique hors-ligne, le projet inclut les sources d’aide CHM dans `docs\help\`. Après installation de HTML Help Workshop, générez `docs\eLib.chm` avec `.\tools\build_chm.ps1`.

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
   - Les ventes Cité Royale restent visibles dans les chiffres. Un paiement CB est reçu directement par Cité Royale et ne crée pas de dette locale; tout autre mode encaissé par un libraire reste à régulariser sur PayPal POS.
   - Suivi des reversements réellement dus aux autres origines et historique des règlements partiels ou totaux.
   - La CB du stock local est désactivée par défaut et peut être activée dans *Données & Excel* lorsque le TPE local sera disponible.

4. **Catalogue & Packs** :
   - Fiches livres complètes (ISBN, titre, série, volume, auteur, éditeur, prix, seuil d'alerte).
   - L'OCR peut reconnaître un titre déjà au catalogue et proposer de compléter sa fiche ou de lui rattacher le code-barres scanné ; les informations existantes ne sont pas écrasées.
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

### 📋 Choisir votre parcours

- **Obligatoire pour utiliser la caisse :** récupérer et lancer `eLib.exe`. Aucun Python, WebView2 ou moteur OCR séparé n'est à installer sur le PC.
- **Seulement si vous migrez vers un autre PC :** copier le dossier `data/` de l'ancien PC avant le premier démarrage, afin de conserver le catalogue, le stock et les ventes.
- **Optionnel :** configurer le scanner mobile. Le réseau commun, le profil Windows privé, les certificats et la règle de pare-feu ne sont nécessaires que pour cette fonction.
- **Mainteneur uniquement :** compiler depuis les sources avec Python Windows x86 (voir ci-dessous).

---

### 🖥️ Parcours A — Utiliser l'application distribuée (recommandé)

La distribution est un exécutable Windows x86 autonome nommé `eLib.exe`, qui fonctionne sur Windows 32-bit comme 64-bit. Il embarque Python, RapidOCR, ONNX Runtime, les modèles OCR et le runtime WebView2. **Le PC de caisse n'a besoin ni de Python, ni d'un moteur OCR, ni d'une installation WebView2.** Internet n'est pas requis pour encaisser; il est nécessaire pour vérifier et télécharger les mises à jour.

1. Copiez `eLib.exe` sur le PC de caisse et lancez-le.
2. Pour reprendre une installation existante sur un nouveau PC, copiez également le dossier `data/` de l'ancien PC à côté de `eLib.exe` avant le lancement. Pour une nouvelle installation, l'application crée ce dossier automatiquement.

La fenêtre native utilise le runtime WebView2 Fixed Version embarqué ; elle ne dépend donc pas d'un runtime préinstallé et ne bascule pas silencieusement vers le navigateur.

### 🛠️ Parcours B — Compiler depuis les sources (mainteneur uniquement)
RapidOCR x86 nécessite une chaîne de versions compatible : Python 3.10 32-bit, RapidOCR 1.4.4 et ONNX Runtime 1.16.3. Installez Python 3.10 **32-bit (x86)** sur le PC de développement (il peut coexister avec Python 64-bit), puis depuis PowerShell à la racine du projet, lancez :
```powershell
py -3.10-32 tools\build_windows_x86.py
```
Le script installe les dépendances binaires épinglées, télécharge et vérifie le package Microsoft WebView2 Fixed Version x86, puis construit `dist_win32\eLib.exe`. Les bibliothèques natives, le runtime WebView2, les modèles OCR et Python sont intégrés dans l'exécutable. Le runtime WebView2 est volumineux (plus de 250 Mo décompressé) et doit être mis à jour périodiquement avec l'application pour recevoir les correctifs de sécurité. Les utilisateurs finaux n'ont besoin d'aucun de ces outils ni d'une connexion Internet.

Pour produire la distribution portable (`eLib-Portable-<version>.zip` : exécutable + LISEZ-MOI.txt, sans installation), lancez ensuite :
```powershell
python tools\package_portable_win32.py
```
L'archive est aussi publiée automatiquement en même temps que `eLib.exe` lors d'un tag de version. Le dossier `data/` local n'est jamais inclus dans l'archive.

**Important :** `dist_win32\` est un dossier de sortie de compilation, pas un dossier d'exécution. Ne lancez jamais `eLib.exe` depuis `dist_win32\` : l'application créerait son dossier `data/` de travail à côté de l'exécutable et polluerait les artefacts de distribution. Pour tester un build, copiez `eLib.exe` dans un dossier de test séparé (par exemple `C:\eLib_test\`) et lancez-le de là.

Pour produire l'installateur Windows (`eLib-Setup-<version>.exe` : installation dans Program Files (x86), raccourcis du menu Démarrer, entrée gérée par Windows dans « Applications et fonctionnalités », désinstallation propre), lancez :
```powershell
python tools\build_installer_win32.py
```
Requiert Inno Setup 6 ou 7. Points propres à la version installée :
- les données sont enregistrées dans `C:\ProgramData\eLib` (Program Files n'est pas inscriptible par l'application) ; l'emplacement est écrit dans `elib-data-location.txt` à côté de l'exécutable ;
- la mise à jour automatique continue de fonctionner sans relance UAC (le dossier d'application est inscriptible par les utilisateurs) ;
- la désinstallation ne supprime **jamais** le dossier de données ;
- pour reprendre les données d'une version portable existante, copiez le contenu de l'ancien dossier `data/` vers `C:\ProgramData\eLib` avant le premier lancement.

**Note de maintenance :** la roue ONNX Runtime Windows x86 disponible est ancienne et le projet ONNX Runtime ne prend plus en charge les builds 32-bit actuels. Ces versions sont épinglées pour maintenir la compatibilité x86 et doivent être réévaluées si un runtime x86 plus récent devient disponible.

#### Releases et mises à jour
Les versions publiées sous un tag `vX.Y.Z` sont construites automatiquement par GitHub Actions avec Python 3.10 x86 et publiées comme `eLib.exe` avec un fichier SHA-256. Pour publier une version, fusionnez-la dans la branche de référence, puis créez et poussez un tag de version, par exemple `git tag v1.0.0` puis `git push origin v1.0.0`. Une application distribuée vérifie les versions stables au démarrage puis une fois par jour ; elle ne télécharge qu'après confirmation et ne remplace/redémarre l'application qu'après une seconde confirmation. La connexion Internet est nécessaire pour vérifier et télécharger une version, mais pas pour utiliser eLib. Le SHA-256 détecte les téléchargements altérés ; il ne remplace pas une signature Authenticode de l'éditeur.

Avant la première migration d'une base existante, eLib en crée une copie vérifiée sous `data\sauvegardes\librairie_pre_migration_*.db` ; la base séparée des appareils appairés est aussi sauvegardée sous `devices_pre_migration_*.db` si son schéma doit évoluer. Les migrations sont exécutées au démarrage et la version de la base métier est conservée dans `PRAGMA user_version`. Toute nouvelle évolution de schéma doit incrémenter `LATEST_SCHEMA_VERSION` et ajouter une migration correspondante dans `app/db.py`.

---

### 📱 Parcours optionnel — Configurer le Scanner Mobile (une fois par lieu)

Ignorez toute cette section si la caisse est utilisée uniquement sur le PC. Pour permettre aux bénévoles d'utiliser l'appareil photo de leur smartphone comme douchette :

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

### 🚀 Lancer la caisse

Pour la version distribuée, lancez directement `eLib.exe`. Si vous êtes mainteneur et lancez le projet depuis ses sources, double-cliquez sur :
```text
Lancer_Librairie.bat
```
*(Ou en ligne de commande, avec Python 3.10 32-bit et les dépendances installées : `python run.py`)*

1. L'application démarre le serveur local et s'ouvre dans une fenêtre dédiée (ou votre navigateur sur `http://127.0.0.1:8765`).
2. Pour le parcours mobile seulement, l'écoute HTTPS utilise le port 8766.

---

### 📲 Scanner Mobile — Appairer les smartphones

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
- `requirements.txt` : Dépendances Python, dont les versions x86 épinglées de RapidOCR et ONNX Runtime.
