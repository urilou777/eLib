"""Package the portable distribution: eLib.exe + LISEZ-MOI.txt in a versioned zip.

La version portable est le même exécutable autonome que la version publiée, mais
distribué sous forme d'archive auto-suffisante à décompresser n'importe où
(clé USB, dossier Bureau, second PC) sans installation.

Règles strictes :
- l'archive contient UNIQUEMENT eLib.exe et LISEZ-MOI.txt : jamais le dossier
  data/ voisin (il peut contenir la base réelle de la librairie) ;
- eLib.exe doit être un binaire x86 (PE machine 0x014C), comme la version publiée ;
- une empreinte SHA-256 accompagne l'archive au format utilisé par l'updater.
"""
import hashlib
import os
import re
import struct
import sys
import zipfile

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIST_DIR = os.path.join(PROJECT_DIR, "dist_win32")
EXE_PATH = os.path.join(DIST_DIR, "eLib.exe")

README_TEXT = """eLib – version portable
========================

Aucune installation n'est nécessaire : décompressez l'archive où vous voulez
(Bureau, dossier Documents, clé USB) et double-cliquez sur eLib.exe.

Points importants :
- Toutes les données (base de la librairie, appairages des téléphones, certificats
  HTTPS et sauvegardes) sont enregistrées dans le sous-dossier « data » créé à
  côté de eLib.exe.
- Pour changer d'ordinateur ou utiliser une clé USB : copiez TOUJOURS le dossier
  complet (eLib.exe + data), jamais l'exécutable seul.
- Les sauvegardes automatiques (miroir Excel + instantanés quotidiens de la base)
  se trouvent dans data\\sauvegardes.
- WebView2 et les modèles OCR sont intégrés : aucune connexion Internet n'est
  requise pour utiliser l'application.
- Les mises à jour restent automatiques : si une nouvelle version est publiée,
  eLib.exe sera remplacé au redémarrage de l'application, sans toucher à vos
  données.
"""


def pe_machine(path):
    try:
        with open(path, "rb") as executable:
            executable.seek(0x3C)
            header_offset = struct.unpack("<I", executable.read(4))[0]
            executable.seek(header_offset)
            signature = executable.read(4)
            machine = struct.unpack("<H", executable.read(2))[0]
    except (OSError, struct.error) as error:
        raise RuntimeError(f"Invalid Windows executable: {path}") from error
    if signature != b"PE\0\0":
        raise RuntimeError(f"Invalid Windows PE executable: {path}")
    return machine


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def app_version():
    version_path = os.path.join(PROJECT_DIR, "app", "version.py")
    with open(version_path, "r", encoding="utf-8") as source:
        match = re.search(r'VERSION\s*=\s*"([^"]+)"', source.read())
    if not match:
        raise RuntimeError(f"No VERSION found in {version_path}")
    return match.group(1)


def package():
    if not os.path.isfile(EXE_PATH):
        raise RuntimeError(f"Build first: {EXE_PATH} is missing (run tools/build_windows_x86.py).")
    if pe_machine(EXE_PATH) != 0x014C:
        raise RuntimeError(f"Expected an x86 executable: {EXE_PATH}")

    version = app_version()
    zip_name = f"eLib-Portable-{version}.zip"
    zip_path = os.path.join(DIST_DIR, zip_name)

    # Contenu strictement contrôlé : jamais le dossier data/ voisin (base réelle).
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(EXE_PATH, "eLib.exe")
        archive.writestr("LISEZ-MOI.txt", README_TEXT)

    digest = file_sha256(zip_path)
    sha_path = zip_path + ".sha256"
    with open(sha_path, "w", encoding="ascii", newline="\n") as checksum:
        checksum.write(f"{digest}  {zip_name}\n")

    print(f"[Portable-32bit] Archive : {zip_path}")
    print(f"[Portable-32bit] Empreinte : {sha_path}")
    return zip_path


if __name__ == "__main__":
    try:
        package()
    except (OSError, RuntimeError) as error:
        print(f"[Portable-32bit] ERROR: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
