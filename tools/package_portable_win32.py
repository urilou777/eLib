"""Package the portable distribution: a single self-contained, versioned exe.

La version portable embarque TOUT (runtime WebView2 inclus) dans un exe unique
publié directement : un seul fichier à télécharger, un seul exe à lancer, sans
installation. Contrepartie assumée et documentée dans les notes de release :
démarrage plus lent (~10 s) que la version installée (~3 s), car Windows doit
décompresser le runtime embarqué à chaque lancement.

Règles strictes :
- l'exe portable est construit avec ELIB_BUNDLE_RUNTIME=1 (runtime inclus) ;
- il doit être un binaire x86 (PE machine 0x014C), comme la version publiée ;
- une empreinte SHA-256 accompagne l'exe au format utilisé par l'updater.
"""
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIST_DIR = os.path.join(PROJECT_DIR, "dist_win32")

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
    """Construit l'exe portable autonome (runtime embarqué) puis l'archive.

    La version portable encapsule TOUT dans un seul exécutable : aucun dossier à
    copier, aucune installation. Contrepartie assumée et documentée : à chaque
    lancement, Windows doit décompresser le runtime embarqué (~10 s), là où la
    version installée démarre en ~3 s grâce au dossier webview2/ posé une fois.
    """
    portable_exe = os.path.join(DIST_DIR, "eLib-Portable.exe")
    if not os.path.isfile(portable_exe) or pe_machine(portable_exe) != 0x014C:
        print("[Portable-32bit] Construction de l'exe autonome (runtime embarque)...", flush=True)
        env = dict(os.environ, ELIB_BUNDLE_RUNTIME="1")
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "--distpath", DIST_DIR, "--workpath",
             os.path.join(PROJECT_DIR, "build_win32"),
             os.path.join(PROJECT_DIR, "eLib.spec")],
            cwd=PROJECT_DIR, env=env, check=True,
        )
        if not os.path.isfile(portable_exe) or pe_machine(portable_exe) != 0x014C:
            raise RuntimeError(f"PyInstaller n'a pas produit l'attendu : {portable_exe}")

    version = app_version()
    # Signature Authenticode si un certificat est configuré, avant l'empreinte.
    from sign_binaries import sign_file

    sign_file(portable_exe)

    # Publication directe de l'exe portable (pas de zip : un seul fichier à
    # télécharger, un seul exe à lancer). La mention « démarrage plus lent »
    # vit dans les notes de release plutôt que dans un LISEZ-MOI.
    release_name = f"eLib-Portable-{version}.exe"
    release_path = os.path.join(DIST_DIR, release_name)
    if os.path.exists(release_path):
        os.remove(release_path)
    shutil.copyfile(portable_exe, release_path)

    sha_path = release_path + ".sha256"
    with open(sha_path, "w", encoding="ascii", newline="\n") as checksum:
        checksum.write(f"{file_sha256(release_path)}  {release_name}\n")

    print(f"[Portable-32bit] Exe portable : {release_path}")
    print(f"[Portable-32bit] Empreinte : {sha_path}")
    return release_path


if __name__ == "__main__":
    try:
        package()
    except (OSError, RuntimeError) as error:
        print(f"[Portable-32bit] ERROR: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
