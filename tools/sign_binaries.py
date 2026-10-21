"""Signature Authenticode (signtool) des binaires distribués.

Active automatiquement la signature dès qu'un certificat est configuré :
- ELIB_SIGN_PFX : chemin du fichier .pfx, OU contenu du certificat encodé
  en base64 (pratique pour un secret GitHub Actions) ;
- ELIB_SIGN_PWD : mot de passe du certificat.
Sans ces variables, la signature est ignorée proprement (binaire non signé).

La signature supprime les avertissements SmartScreen / Contrôle d'application
intelligent de Windows : c'est la seule correction réelle de ces avertissements,
et la réputation se construit automatiquement avec les téléchargements.
"""
import base64
import glob
import os
import subprocess
import sys
import tempfile

TIMESTAMP_SERVER = "http://timestamp.digicert.com"


def find_signtool():
    for arch in ("x64", "x86"):
        pattern = os.path.join(
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            "Windows Kits", "10", "bin", "*", arch, "signtool.exe",
        )
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]
    raise RuntimeError("signtool.exe introuvable (Windows SDK requis).")


def signing_enabled():
    return bool((os.environ.get("ELIB_SIGN_PFX") or "").strip())


def sign_file(path):
    """Signe un fichier avec le certificat configuré. No-op si non configuré."""
    if not signing_enabled():
        return False
    value = (os.environ.get("ELIB_SIGN_PFX") or "").strip()
    pfx = value if os.path.isfile(value) else None
    is_temp = pfx is None
    if is_temp:
        fd, pfx = tempfile.mkstemp(suffix=".pfx")
        with os.fdopen(fd, "wb") as sink:
            sink.write(base64.b64decode(value))
    try:
        subprocess.run(
            [
                find_signtool(), "sign",
                "/fd", "SHA256",
                "/td", "SHA256", "/tr", TIMESTAMP_SERVER,
                "/f", pfx,
                "/p", os.environ.get("ELIB_SIGN_PWD") or "",
                path,
            ],
            check=True,
        )
        print(f"[Signature] {path} signé", flush=True)
        return True
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"Échec de signature de {path} (code {error.returncode}).") from error
    finally:
        if is_temp:
            try:
                os.remove(pfx)
            except OSError:
                pass


if __name__ == "__main__":
    if not signing_enabled():
        print("[Signature] Aucun certificat configuré (ELIB_SIGN_PFX/ELIB_SIGN_PWD) : pas de signature.")
        sys.exit(0)
    for target in sys.argv[1:]:
        sign_file(target)
