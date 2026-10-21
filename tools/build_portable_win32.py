"""Build an embedded Python 3.10 x86 runtime with the pinned RapidOCR stack."""
import glob
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

DEFAULT_VERSION = "3.10.11"
PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNTIME_DIR = os.path.join(PROJECT_DIR, "runtime_win32")


def log(msg):
    print(f"[Portable-32bit] {msg}", flush=True)


def build_portable(version=DEFAULT_VERSION):
    ver_short = "".join(version.split(".")[:2])  # ex: '310'
    embed_url = f"https://www.python.org/ftp/python/{version}/python-{version}-embed-win32.zip"

    log(f"Préparation de l'environnement Python {version} (32-bit x86) dans : {RUNTIME_DIR}")
    
    # Nettoyer l'ancien runtime si version différente
    if os.path.exists(RUNTIME_DIR):
        log("Nettoyage de l'ancien dossier runtime_win32...")
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)
    os.makedirs(RUNTIME_DIR, exist_ok=True)

    # 1. Télécharger l'archive embeddable 32-bit officielle
    zip_path = os.path.join(RUNTIME_DIR, "python-embed-win32.zip")
    log(f"Téléchargement de Python {version} embeddable 32-bit depuis python.org...")
    urllib.request.urlretrieve(embed_url, zip_path)
    log("Extraction des fichiers système Python 32-bit...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(RUNTIME_DIR)
    try:
        os.remove(zip_path)
    except OSError:
        pass

    # 2. Activer site-packages dans python*._pth
    pth_files = glob.glob(os.path.join(RUNTIME_DIR, "python*._pth"))
    for pth_file in pth_files:
        with open(pth_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = []
        for line in lines:
            if line.strip() in ("#import site", "# import site"):
                new_lines.append("import site\n")
            elif line.strip() == "import site":
                new_lines.append(line)
            else:
                new_lines.append(line)
        if "import site\n" not in new_lines:
            new_lines.append("import site\n")
        if ".\n" not in new_lines and "." not in [l.strip() for l in new_lines]:
            new_lines.insert(0, ".\n")
        if "..\n" not in new_lines and ".." not in [l.strip() for l in new_lines]:
            new_lines.insert(1, "..\n")
        if "Lib/site-packages\n" not in new_lines:
            new_lines.append("Lib/site-packages\n")
        with open(pth_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        log(f"Fichier {os.path.basename(pth_file)} configuré pour charger site-packages.")

    # 3. Créer Lib/site-packages
    site_packages = os.path.join(RUNTIME_DIR, "Lib", "site-packages")
    os.makedirs(site_packages, exist_ok=True)

    # 4. Pré-construire les roues pure-python manquantes (proxy_tools pour pywebview)
    wheels_dir = os.path.join(RUNTIME_DIR, ".tmp_wheels")
    os.makedirs(wheels_dir, exist_ok=True)
    subprocess.run([sys.executable, "-m", "pip", "wheel", "proxy_tools", "bottle", "--no-deps", "-w", wheels_dir], capture_output=True)

    # 5. Installer les dépendances 32-bit via pip --target
    log(f"Installation des dépendances 32-bit (version {ver_short}) dans site-packages...")
    req_file = os.path.join(PROJECT_DIR, "requirements.txt")
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--target", site_packages,
        "--platform", "win32",
        "--python-version", ver_short,
        "--only-binary=:all:",
        "--find-links", wheels_dir,
        "-r", req_file,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    shutil.rmtree(wheels_dir, ignore_errors=True)
    if res.returncode != 0:
        log(f"Erreur pip: {res.stderr}")
        return 1

    log(f"Succès ! L'environnement portable Python {version} (32-bit) est prêt.")
    log(f"Emplacement : {RUNTIME_DIR}")
    log("Lancer_eLib.bat utilisera automatiquement ce runtime 32-bit.")
    return 0


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VERSION
    return build_portable(version)


if __name__ == "__main__":
    sys.exit(main())
