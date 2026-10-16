# Bibliothèques tierces embarquées (hors-ligne, sans CDN)

| Fichier | Source | Version | SHA-256 |
|---|---|---|---|
| `zxing.min.js` | https://unpkg.com/@zxing/library@0.21.3/umd/index.min.js (npm `@zxing/library`, Apache-2.0) | 0.21.3 (épinglée) | `D7CC8F69DD70BDCF3AC00C9AE572BF2ACB9F4132BA379C72DF842E4DB918652D` |

Pourquoi embarquée : aucune dépendance Internet (cahier des charges hors-ligne), aucune exécution de code
distant (`@latest` sur un CDN = risque « supply chain »), et la CSP de l'écran mobile interdit tout script externe.

Mise à jour : télécharger la nouvelle version, recalculer le SHA-256 (`Get-FileHash`), mettre ce tableau à jour,
vérifier l'absence de `eval(` / `new Function(` (la CSP mobile n'autorise pas `unsafe-eval`).
