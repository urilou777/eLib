# Architecture Technique & Guide de Transmission : Scanner Mobile & HTTPS

Ce document détaille l'architecture complète du **Scanner Mobile** (HTTPS local, PKI, sécurité réseau et moteur de scan multi-échelles), ainsi que les procédures de transmission et de maintenance simplifiées au maximum pour les personnes qui prendront le relais après vous.

---

## 🏛️ 1. Schéma d'Architecture Globale

L'application respecte le principe du **moindre privilège réseau** et fonctionne **100% hors-ligne** (aucune connexion Internet requise, zéro dépendance Cloud).

```
 +-----------------------------------------------------------------------------------------------+
 |                                  ORDINATEUR CENTRAL DE CAISSE                                 |
 |                                                                                               |
 |   +------------------------------------+          +---------------------------------------+   |
 |   |          BUREAU & ADMIN            |          |        SCANNER MOBILE SÉCURISÉ        |   |
 |   |      http://127.0.0.1:8765         |          |     https://172.21.36.137:8766        |   |
 |   |        (Poste de caisse)           |          |         (Réseau local Wi-Fi)          |   |
 |   +-----------------+------------------+          +-------------------+-------------------+   |
 |                     |                                                 |                       |
 |                     v                                                 v                       |
 |        [ FastAPI : loopback_only ]                        [ FastAPI : security_gate ]         |
 |         - Sauvegardes & Restauration                       - Appairage (Jeton Bearer)         |
 |         - Import / Export Excel                            - Scan code-barres                 |
 |         - Gestion trésorerie / admin                       - Enregistrement des ventes        |
 |                     |                                                 |                       |
 |                     +------------------------+------------------------+                       |
 |                                              |                                                |
 |                                              v                                                |
 |                             +----------------------------------+                              |
 |                             |  SQLite WAL (Write-Ahead-Log)    |                              |
 |                             |   data/librairie.db (Transactions|                              |
 |                             |   data/devices.db   (Appairages) |                              |
 |                             +----------------------------------+                              |
 +----------------------------------------------^------------------------------------------------+
                                                |
                                                |  Connexion Wi-Fi Local (HTTPS TLS 1.3)
                                                |  Port 8766 restreint au sous-réseau
                                                v
               +------------------------------------------------------------------+
               |                  SMARTPHONES DES LIBRAIRES                       |
               |             (iPhone Safari / Android Chrome / S24)               |
               |                                                                  |
               |   [ PWA Hors-Ligne ] <---> [ Moteur Scan Multi-Échelles 1:1 ]    |
               |   - Identité libraire       - Échelle A : Macro 2x (petits codes)|
               |   - Choix manuel des lots   - Échelle B : Cadrage large (grands) |
               |   - Jeton d'accès Bearer    - Binarisation anti-reflets          |
               +------------------------------------------------------------------+
```

---

## 🔐 2. Le Système HTTPS & PKI Locale (Comment ça marche)

### Pourquoi du HTTPS en local ?
Sur tous les smartphones modernes (iOS et Android), les navigateurs web **interdisent formellement l'accès à la caméra (`getUserMedia`)** si la page n'est pas servie sous un contexte sécurisé (`https://` ou `localhost`). Comme le smartphone accède au PC via le Wi-Fi local (ex: `172.21.36.137`), le HTTPS est **obligatoire**.

### Le système d'auto-renouvellement transparent (`app/certs.py`)
Pour que vos successeurs **n'aient jamais à générer manuellement un certificat OpenSSL**, le système est entièrement automatisé :

1. **L'Autorité Racine Locale (CA) :**
   - Générée automatiquement lors du premier lancement dans `data/certs/Librairie-CA.crt`.
   - Clé privée ECC P-256 (ultra-légère et inviolable).
   - Validité de **5 ans**.
   - **Name-constrained** : la CA ne peut signer que pour les IP privées locales (`192.168.*`, `10.*`, `172.16-31.*`, `localhost`). Elle est inoffensive pour le reste d'Internet.
2. **Le Certificat Serveur dynamique :**
   - Détecte automatiquement l'IP locale de la machine à chaque démarrage.
   - S'auto-renouvelle **automatiquement et sans action humaine** dès que :
     - L'adresse IP de la box Wi-Fi change.
     - Le certificat arrive à moins de 30 jours de son expiration.
   - Ajoute tous les noms alternatifs (SANs) : `127.0.0.1`, `<nom-pc>.local`, et l'adresse IP Wi-Fi active.

---

## ⚡ 3. Architecture du Moteur de Scan Multi-Échelles

```
              Flux Caméra Haute Définition (1080p natif)
                                 │
                                 ▼
                    Inspection ROI au Centre
                                 │
         ┌───────────────────────┴───────────────────────┐
         ▼                                               ▼
[ Échelle Macro 2x (38% du centre) ]    [ Échelle Large (72% du centre) ]
  - Petits codes-barres de poche          - Grands formats / BDs
  - Haute densité de pixels (DPI 1:1)     - Distance normale (20 cm)
  - Zéro flou de macro                    - Couverture totale
         │                                               │
         └───────────────────────┬───────────────────────┘
                                 │
                                 ▼
          Pipeline de Traitement pour Conditions Dégradées
                                 │
 1. Détection directe native (BarcodeDetector Chromium)
 2. Binarisation heuristique ZXing (TRY_HARDER)
 3. Netteté 1D horizontale (Anti-flou de bougé)
 4. Binarisation adaptative de Bradley-Roth (Anti-reflets & ombres néon)
                                 │
                                 ▼
               Validation Mathématique Modulo-10
                (Garantit zéro faux-positif)
                                 │
                                 ▼
                Ajout Immédiat au Panier Mobile
```

---

## 📋 4. Guide de Passation & Transmission (Pour vos successeurs)

> **Ce qu'il faut retenir en une phrase :**  
> Tout est automatisé. Si un nouveau téléphone arrive, il suffit de lui faire scanner le QR code affiché dans la caisse du PC.

### Scénario A : Un nouveau bénévole/libraire arrive avec son téléphone
1. Sur le PC, ouvrir la Librairie et cliquer sur l'onglet **Caisse**.
2. Cliquer sur le bouton **📱 Ouvrir Scanner Mobile** en haut à droite.
3. Le bénévole ouvre l'appareil photo de son smartphone (connecté au même Wi-Fi).
4. Il scanne le QR code.
5. Sur son téléphone :
   - Le navigateur s'ouvre sur `https://...`.
   - Il clique sur **« Continuer vers le site »** (ou installe une fois `Librairie-CA.crt`).
   - Il choisit son prénom dans la liste. C'est prêt !

### Scénario B : La box Wi-Fi ou l'ordinateur change d'adresse IP
- **Action nécessaire : AUCUNE.**
- `app/certs.py` détecte automatiquement la nouvelle IP au démarrage du logiciel et génère un certificat serveur à jour en 0.2 seconde.

### Scénario C : Le certificat arrive à expiration dans quelques années
- **Action nécessaire : AUCUNE.**
- L'application vérifie la date de validité à chaque démarrage. Si le certificat serveur approche de la fin, il est réémis automatiquement sans intervention.

### Scénario D : L'ordinateur de caisse a été réinstallé (Nouveau PC)
1. Télécharger ou copier le dossier `librairie` sur le nouveau PC.
2. Double-cliquer sur :
   ```text
   Installer_Mobile.bat
   ```
   *(Ce script configure la règle de pare-feu Windows et initialise les certificats)*.
3. Lancer la caisse avec **`Lancer_eLib.bat`**.

---

## 🛡️ 5. Résumé des Mesures de Sécurité Appliquées

| Composant | Protection mise en place |
| :--- | :--- |
| **Isolation Réseau** | Les fonctions d'administration (sauvegardes, imports, trésorerie) refusent les connexions Wi-Fi et n'acceptent que `127.0.0.1`. |
| **Anti-DNS Rebinding** | Le middleware `security_gate` rejette toute requête avec un `Host` non autorisé (Code HTTP 421). |
| **Authentification Smartphone** | Chaque téléphone reçoit un jeton cryptographique stocké sous forme de hachage SHA-256 dans `data/devices.db`. Aucun mot de passe vulnérable à mémoriser. |
| **Pare-feu Windows** | Règle `Librairie Mobile HTTPS (8766)` restreinte au profil privé et au sous-réseau local (`localsubnet`). Le reste du monde est bloqué. |
| **Énergie & Veille** | Appel Windows natif `SetThreadExecutionState` : empêche le PC de s'endormir pendant les ventes, veille automatique du capteur smartphone après 90s d'inactivité. |
