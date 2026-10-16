"""Script de configuration et d'installation du scanner mobile sécurisé.
Génère le certificat TLS local pour les adresses IP du PC et configure le pare-feu Windows.
Nécessite des privilèges Administrateur pour la règle de pare-feu.
"""
import ctypes
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PORT = 8766
RULE_NAME = f"Librairie Mobile HTTPS ({PORT})"


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_as_admin():
    if is_admin():
        return True
    print("[*] Élévation des privilèges requise pour configurer le pare-feu Windows...")
    params = f'"{Path(__file__).resolve()}" ' + " ".join(f'"{a}"' for a in sys.argv[1:])
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, str(BASE_DIR), 1
    )
    return ret > 32


def setup_certs():
    sys.path.insert(0, str(BASE_DIR))
    from app import certs, security

    ips = security.local_ips()
    print(f"\n[1/3] Détection des adresses IP locales : {ips or ['Aucune IP privée détectée']}")

    cert_path, key_path = certs.ensure_server_cert(ips)
    fp = certs.ca_fingerprint()
    print(f"[2/3] Certificats TLS vérifiés/générés avec succès :")
    print(f"      - Autorité Racine (CA) : {certs.CA_CERT}")
    print(f"      - Empreinte SHA-256    : {fp}")
    print(f"      - Certificat Serveur   : {cert_path}")
    print(f"      - Clé Serveur          : {key_path}")
    return {"cert": cert_path, "key": key_path, "ca": certs.CA_CERT, "fingerprint": fp}



def setup_firewall(uninstall=False):
    print(f"\n[3/3] Configuration du pare-feu Windows (Port TCP {PORT})...")
    # Supprimer l'ancienne règle si elle existe
    subprocess.run(
        f'netsh advfirewall firewall delete rule name="{RULE_NAME}"',
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if uninstall:
        print(f"      Règle de pare-feu '{RULE_NAME}' supprimée.")
        return

    # Création de la règle restreinte au profil privé et au sous-réseau local (LocalSubnet)
    cmd = (
        f'netsh advfirewall firewall add rule name="{RULE_NAME}" '
        f'dir=in action=allow protocol=TCP localport={PORT} '
        f'profile=private remoteip=localsubnet description="Autorise les smartphones locaux à se connecter au scanner mobile Librairie"'
    )
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if proc.returncode == 0:
        print(f"      [OK] Règle de pare-feu ajoutée avec succès (profil privé, sous-réseau local uniquement).")
    else:
        print(f"      [!] Attention : Impossible d'ajouter la règle de pare-feu automatique.")
        print(f"          Détail : {proc.stderr or proc.stdout}")

    # Vérification du profil de connexion réseau Wi-Fi / Ethernet
    try:
        ps_cmd = 'powershell -NoProfile -Command "Get-NetConnectionProfile | Select-Object -Property InterfaceAlias, NetworkCategory | Format-Table -HideTableHeaders"'
        p = subprocess.run(ps_cmd, shell=True, capture_output=True, text=True)
        if "Public" in p.stdout:
            print("\n[!] AVERTISSEMENT IMPORTANT :")
            print("    Votre connexion réseau actuelle semble définie en 'Réseau Public' dans Windows.")
            print("    Pour que vos smartphones puissent accéder à l'ordinateur :")
            print("    Allez dans Paramètres Windows > Réseau et Internet > Wi-Fi (ou Ethernet)")
            print("    et changez le type de profil réseau en 'Réseau Privé'.")
    except Exception:
        pass


def main():
    uninstall = "--uninstall" in sys.argv
    if not is_admin():
        if not run_as_admin():
            print("[!] Impossible d'obtenir les droits Administrateur. Le pare-feu n'a pas pu être configuré.")
            if not uninstall:
                setup_certs()
        sys.exit(0)

    if uninstall:
        setup_firewall(uninstall=True)
        print("\nDésinstallation terminée.")
        input("\nAppuyez sur Entrée pour quitter...")
        return

    print("=" * 65)
    print("  INSTALLATION DU SCANNER MOBILE ET CONFIGURATION SÉCURISÉE")
    print("=" * 65)

    try:
        setup_certs()
        setup_firewall()
        print("\n" + "=" * 65)
        print("  [SUCCÈS] Installation terminée !")
        print("  Vous pouvez maintenant démarrer ou redémarrer la Librairie.")
        print("=" * 65)
    except Exception as e:
        print(f"\n[ERREUR] Une erreur est survenue : {e}")
        import traceback
        traceback.print_exc()

    input("\nAppuyez sur Entrée pour fermer cette fenêtre...")


if __name__ == "__main__":
    main()
