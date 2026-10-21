r"""Build the Windows installer (setup.exe) with Inno Setup from dist_win32\eLib.exe.

Produit dist_win32\eLib-Setup-<version>.exe + empreinte SHA-256.
Requiert Inno Setup 6 ou 7 (https://jrsoftware.org/isinfo.php) ; sur le runner GitHub
il est installé via `choco install innosetup`. Localement, installez-le ou
définissez ELIB_ISCC vers ISCC.exe.
"""
import hashlib
import os
import re
import struct
import subprocess
import sys

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIST_DIR = os.path.join(PROJECT_DIR, "dist_win32")
EXE_PATH = os.path.join(DIST_DIR, "eLib.exe")
ISS_PATH = os.path.join(PROJECT_DIR, "installer", "eLib.iss")


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


def find_iscc():
    candidates = [os.environ.get("ELIB_ISCC")]
    for program_files in (
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramW6432"),
    ):
        if program_files:
            for major in ("7", "6"):
                candidates.append(os.path.join(program_files, f"Inno Setup {major}", "ISCC.exe"))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise RuntimeError(
        "Inno Setup 6 ou 7 introuvable (ISCC.exe). Installez-le depuis "
        "https://jrsoftware.org/isinfo.php ou définissez ELIB_ISCC."
    )


def _compile(iscc, extra_defines, label):
    command = [iscc] + [f"/D{key}={value}" for key, value in extra_defines] + [ISS_PATH]
    print(f"[Installer-32bit] Compilation {label} : {' '.join(command[1:-1])}", flush=True)
    subprocess.run(command, cwd=PROJECT_DIR, check=True)


def _emit_sha(setup_path):
    sha_path = setup_path + ".sha256"
    with open(sha_path, "w", encoding="ascii", newline="\n") as checksum:
        checksum.write(f"{file_sha256(setup_path)}  {os.path.basename(setup_path)}\n")
    return sha_path


def build_installer():
    if not os.path.isfile(EXE_PATH):
        raise RuntimeError(f"Build first: {EXE_PATH} is missing (run tools/build_windows_x86.py).")
    if pe_machine(EXE_PATH) != 0x014C:
        raise RuntimeError(f"Expected an x86 executable: {EXE_PATH}")

    version = app_version()
    iscc = find_iscc()
    print(f"[Installer-32bit] Inno Setup : {iscc}", flush=True)

    # Setup web (~2 Mo) : n'embarque pas eLib.exe, le télécharge depuis la release
    # GitHub et vérifie son SHA-256. L'empreinte attendue est celle de l'exécutable
    # qui sera publié ; ELIB_PAYLOAD_SHA256 permet de cibler une release déjà publiée.
    payload_sha = os.environ.get("ELIB_PAYLOAD_SHA256") or file_sha256(EXE_PATH)
    _compile(iscc, [("AppVersion", version), ("WebSetup", ""), ("PayloadSha256", payload_sha)], "setup web")
    web_path = os.path.join(DIST_DIR, f"eLib-Setup-{version}.exe")
    if not os.path.isfile(web_path):
        raise RuntimeError(f"Inno Setup n'a pas produit l'attendu : {web_path}")

    # Setup offline (~333 Mo) : embarque eLib.exe pour une installation sans Internet.
    _compile(iscc, [("AppVersion", version)], "setup offline")
    offline_path = os.path.join(DIST_DIR, f"eLib-Setup-Offline-{version}.exe")
    if not os.path.isfile(offline_path):
        raise RuntimeError(f"Inno Setup n'a pas produit l'attendu : {offline_path}")

    for path in (web_path, offline_path):
        print(f"[Installer-32bit] Installateur : {path}")
        print(f"[Installer-32bit] Empreinte : {_emit_sha(path)}")
    return web_path


if __name__ == "__main__":
    try:
        build_installer()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"[Installer-32bit] ERROR: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
