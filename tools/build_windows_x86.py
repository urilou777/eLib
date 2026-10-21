"""Build the self-contained RapidOCR Windows x86 application."""

import os
import hashlib
import struct
import subprocess
import sys
import urllib.request

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "dist_win32")
WORK_DIR = os.path.join(PROJECT_DIR, "build_win32")
WEBVIEW2_VERSION = "155.0.4283.62"
WEBVIEW2_CAB_URL = (
    "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/"
    "ec2d24c3-2248-48cc-8198-76201ff04abd/"
    f"Microsoft.WebView2.FixedVersionRuntime.{WEBVIEW2_VERSION}.x86.cab"
)
WEBVIEW2_CAB_SHA256 = "866dfe6c1f525d9026413b41a6863da53ad5c8ea9d3142ca54d8e09b36cb183a"
WEBVIEW2_CAB_SIZE = 268595207
WEBVIEW2_CAB = os.path.join(
    WORK_DIR, f"Microsoft.WebView2.FixedVersionRuntime.{WEBVIEW2_VERSION}.x86.cab"
)
WEBVIEW2_RUNTIME_DIR = os.path.join(WORK_DIR, "webview2_runtime")
WEBVIEW2_EXTRACTED_DIR = os.path.join(
    WEBVIEW2_RUNTIME_DIR,
    f"Microsoft.WebView2.FixedVersionRuntime.{WEBVIEW2_VERSION}.x86",
)


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


def ensure_webview2_runtime():
    os.makedirs(WORK_DIR, exist_ok=True)
    if (
        not os.path.isfile(WEBVIEW2_CAB)
        or os.path.getsize(WEBVIEW2_CAB) != WEBVIEW2_CAB_SIZE
        or file_sha256(WEBVIEW2_CAB) != WEBVIEW2_CAB_SHA256
    ):
        partial_path = WEBVIEW2_CAB + ".download"
        print(
            f"[Windows x86 build] Downloading WebView2 Fixed Runtime {WEBVIEW2_VERSION} "
            f"({WEBVIEW2_CAB_SIZE // (1024 * 1024)} MB).",
            flush=True,
        )
        try:
            with urllib.request.urlopen(WEBVIEW2_CAB_URL, timeout=60) as response:
                with open(partial_path, "wb") as destination:
                    while chunk := response.read(1024 * 1024):
                        destination.write(chunk)
            if os.path.getsize(partial_path) != WEBVIEW2_CAB_SIZE:
                raise RuntimeError("Downloaded WebView2 runtime package has an unexpected size.")
            if file_sha256(partial_path) != WEBVIEW2_CAB_SHA256:
                raise RuntimeError("Downloaded WebView2 runtime package failed SHA-256 verification.")
            os.replace(partial_path, WEBVIEW2_CAB)
        finally:
            if os.path.exists(partial_path):
                os.remove(partial_path)

    os.makedirs(WEBVIEW2_EXTRACTED_DIR, exist_ok=True)
    runtime_executable = os.path.join(WEBVIEW2_EXTRACTED_DIR, "msedgewebview2.exe")
    if not os.path.isfile(runtime_executable):
        print("[Windows x86 build] Extracting WebView2 Fixed Runtime.", flush=True)
        subprocess.run(
            ["expand.exe", WEBVIEW2_CAB, "-F:*", WEBVIEW2_RUNTIME_DIR],
            cwd=PROJECT_DIR,
            check=True,
        )
    if not os.path.isfile(runtime_executable):
        raise RuntimeError(
            f"WebView2 runtime extraction did not produce {runtime_executable}."
        )


def build():
    if struct.calcsize("P") != 4:
        raise RuntimeError(
            "Build with Python 3.10 32-bit. The resulting x86 app also runs on 64-bit Windows."
        )
    if sys.version_info[:2] != (3, 10):
        raise RuntimeError(
            f"Use Python 3.10 32-bit for RapidOCR x86; found Python {sys.version.split()[0]}."
        )

    ensure_webview2_runtime()

    print("[Windows x86 build] Installing pinned, prebuilt project dependencies.", flush=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--only-binary=:all:",
            # pywebview >= 4 dépend de proxy_tools, publié uniquement en source :
            # sans cette exception, pip retombe silencieusement sur pywebview 3.4,
            # qui ne possède pas webview.settings et casse la fenêtre au lancement.
            "--no-binary=proxy-tools",
            "-r",
            os.path.join(PROJECT_DIR, "requirements.txt"),
        ],
        cwd=PROJECT_DIR,
        check=True,
    )
    # Garde-fou : refuser de produire un binaire avec un pywebview incompatible.
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import webview; assert hasattr(webview, 'settings'), "
            "'pywebview installe ne possede pas webview.settings'; "
            "from importlib.metadata import version; "
            "assert version('pywebview') == '6.2.1', version('pywebview')",
        ],
        cwd=PROJECT_DIR,
        check=True,
    )

    print("[Windows x86 build] Packaging Python, RapidOCR, ONNX Runtime, and models.", flush=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            OUTPUT_DIR,
            "--workpath",
            WORK_DIR,
            os.path.join(PROJECT_DIR, "eLib.spec"),
        ],
        cwd=PROJECT_DIR,
        check=True,
    )

    executable = os.path.join(OUTPUT_DIR, "eLib.exe")
    if pe_machine(executable) != 0x014C:
        raise RuntimeError(f"PyInstaller produced a non-x86 executable: {executable}")
    print(f"[Windows x86 build] Ready to distribute: {executable}", flush=True)
    print(
        "[Windows x86 build] Python, OCR, models, and WebView2 are bundled; users need no internet.",
        flush=True,
    )


if __name__ == "__main__":
    try:
        build()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"[Windows x86 build] ERROR: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
