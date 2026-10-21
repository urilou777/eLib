"""Check and stage verified GitHub Releases for the frozen Windows application."""

import hashlib
import json
import logging
import os
import re
import struct
import subprocess
import threading
import time
import base64
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .version import VERSION

REPOSITORY = "urilou777/eLib"
RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
CHECK_INTERVAL_SECONDS = 24 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 15
MAX_RELEASE_SIZE = 500 * 1024 * 1024
_VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_USER_AGENT = "eLib-updater"
_LOG = logging.getLogger("elib.updater")


def _version_tuple(version):
    match = _VERSION_PATTERN.fullmatch(version.strip())
    if not match:
        raise ValueError(f"Unsupported release version: {version!r}")
    return tuple(int(part) for part in match.groups())


def _request(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Update URLs must use HTTPS.")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": _USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    return urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS)


def _validate_asset_url(url):
    parsed = urllib.parse.urlparse(url)
    expected_prefix = f"/{REPOSITORY}/releases/download/"
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or not parsed.path.startswith(expected_prefix)
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Release assets must be hosted on this repository's GitHub Releases.")


def get_latest_release():
    with _request(RELEASE_API) as response:
        release = json.loads(response.read().decode("utf-8"))

    if release.get("draft") or release.get("prerelease"):
        return None
    tag_name = release.get("tag_name", "")
    latest_version = _version_tuple(tag_name)
    if latest_version <= _version_tuple(VERSION):
        return None

    assets = {
        asset.get("name"): asset
        for asset in release.get("assets", [])
        if isinstance(asset, dict)
    }
    executable = assets.get("eLib.exe")
    checksum = assets.get("eLib.exe.sha256")
    if not executable or not checksum:
        raise ValueError("The latest GitHub Release is missing eLib.exe or its SHA-256 file.")
    if executable.get("size", 0) <= 0 or executable["size"] > MAX_RELEASE_SIZE:
        raise ValueError("The latest GitHub Release executable has an invalid size.")

    download_url = executable.get("browser_download_url", "")
    checksum_url = checksum.get("browser_download_url", "")
    if not download_url or not checksum_url:
        raise ValueError("The latest GitHub Release has invalid download links.")
    _validate_asset_url(download_url)
    _validate_asset_url(checksum_url)
    return {
        "tag": tag_name,
        "version": ".".join(str(part) for part in latest_version),
        "size": executable["size"],
        "download_url": download_url,
        "checksum_url": checksum_url,
        "api_digest": executable.get("digest"),
    }


def _read_expected_digest(url):
    with _request(url) as response:
        contents = response.read(4096).decode("ascii")
    match = re.fullmatch(r"\s*([0-9a-fA-F]{64})(?:\s+\*?eLib\.exe)?\s*", contents)
    if not match:
        raise ValueError("The release SHA-256 file has an invalid format.")
    return match.group(1).lower()


def _download_release(release, destination):
    expected_digest = _read_expected_digest(release["checksum_url"])
    api_digest = release.get("api_digest")
    if api_digest:
        if not api_digest.startswith("sha256:") or api_digest[7:].lower() != expected_digest:
            raise ValueError("GitHub's asset digest does not match the release checksum.")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".download")
    digest = hashlib.sha256()
    downloaded = 0
    try:
        with _request(release["download_url"]) as response, partial.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > release["size"] or downloaded > MAX_RELEASE_SIZE:
                    raise ValueError("The downloaded release is larger than its declared size.")
                output.write(chunk)
                digest.update(chunk)
        if downloaded != release["size"]:
            raise ValueError(
                f"The release download is incomplete ({downloaded} of {release['size']} bytes)."
            )
        if digest.hexdigest() != expected_digest:
            raise ValueError("The downloaded executable failed SHA-256 verification.")
        try:
            with partial.open("rb") as executable:
                if executable.read(2) != b"MZ":
                    raise ValueError("The downloaded release is not a Windows executable.")
                executable.seek(0x3C)
                header_offset = struct.unpack("<I", executable.read(4))[0]
                executable.seek(header_offset)
                if executable.read(4) != b"PE\0\0" or struct.unpack("<H", executable.read(2))[0] != 0x014C:
                    raise ValueError("The downloaded release is not a Windows x86 executable.")
        except struct.error as error:
            raise ValueError("The downloaded release has an invalid PE header.") from error
        os.replace(partial, destination)
    finally:
        if partial.exists():
            partial.unlink()
    return destination


def _install_script(executable, staged_executable, process_id):
    target = str(Path(executable).resolve())
    staged = str(Path(staged_executable).resolve())
    working_dir = str(Path(target).parent)
    backup = target + ".previous"
    quote = lambda value: "'" + value.replace("'", "''") + "'"
    return f"""
$ErrorActionPreference = 'Stop'
$pidToWait = {int(process_id)}
$target = {quote(target)}
$staged = {quote(staged)}
$backup = {quote(backup)}
$working = {quote(working_dir)}
while (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) {{
    Start-Sleep -Milliseconds 500
}}
if (Test-Path -LiteralPath $backup) {{
    $backup = $target + '.previous.' + (Get-Date -Format 'yyyyMMddHHmmss')
}}
try {{
    Move-Item -LiteralPath $target -Destination $backup
    Move-Item -LiteralPath $staged -Destination $target
    Start-Process -FilePath $target -WorkingDirectory $working
}} catch {{
    if (Test-Path -LiteralPath $backup) {{
        if (Test-Path -LiteralPath $target) {{
            $failed = $target + '.failed.' + (Get-Date -Format 'yyyyMMddHHmmss')
            Move-Item -LiteralPath $target -Destination $failed
        }}
        Move-Item -LiteralPath $backup -Destination $target
    }}
    if (Test-Path -LiteralPath $target) {{
        Start-Process -FilePath $target -WorkingDirectory $working
    }}
    throw
}}
"""


def _start_install(executable, staged_executable, window):
    script = _install_script(executable, staged_executable, os.getpid())
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    log_path = Path(staged_executable).parent / "install.log"
    with log_path.open("a", encoding="utf-8") as log:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded,
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    if window is not None:
        window.destroy()


def _message_box(message, title="eLib — Mise à jour"):
    if os.name != "nt":
        return 0
    import ctypes

    return ctypes.windll.user32.MessageBoxW(
        None,
        message,
        title,
        0x00000004 | 0x00000040 | 0x00000100,
    )


def _write_log(data_dir, message):
    try:
        log_path = Path(data_dir) / "updates.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        _LOG.exception("Could not write update status to %s", data_dir)


def _check_and_offer(executable, data_dir, window):
    try:
        release = get_latest_release()
    except (OSError, urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as error:
        _write_log(data_dir, f"Update check failed: {error}")
        return
    if not release:
        return

    answer = _message_box(
        f"La version {release['version']} d’eLib est disponible.\n\n"
        "La télécharger maintenant ? L’application restera utilisable pendant le téléchargement.",
    )
    if answer != 6:
        return

    staged = Path(data_dir) / "updates" / "eLib.exe"
    try:
        _download_release(release, staged)
    except (OSError, urllib.error.URLError, TimeoutError, ValueError, struct.error) as error:
        _write_log(data_dir, f"Update download failed: {error}")
        _message_box(
            f"Impossible de vérifier ou télécharger eLib {release['version']}.\n\n"
            f"Détail : {error}\n\nConsultez data\\updates.log.",
            "eLib — Échec de mise à jour",
        )
        return

    answer = _message_box(
        f"eLib {release['version']} est téléchargé et son SHA-256 est vérifié.\n\n"
        "Enregistrer vos opérations puis installer et redémarrer maintenant ?",
    )
    if answer != 6:
        return

    try:
        _start_install(executable, staged, window)
    except Exception as error:
        _write_log(data_dir, f"Could not start update installer: {error}")
        _message_box(
            f"L’application n’a pas pu lancer l’installation.\n\nDétail : {error}",
            "eLib — Échec de mise à jour",
        )


def start_update_monitor(executable, data_dir, window):
    """Poll stable GitHub Releases in the background; install only after confirmation."""

    def monitor():
        while True:
            try:
                time.sleep(10)
                _check_and_offer(executable, data_dir, window)
                time.sleep(CHECK_INTERVAL_SECONDS - 10)
            except Exception:
                _LOG.exception("Unexpected update monitor failure")
                time.sleep(CHECK_INTERVAL_SECONDS)

    threading.Thread(target=monitor, name="eLib-update-check", daemon=True).start()
