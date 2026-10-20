"""Build the self-contained RapidOCR Windows x86 application."""

import os
import struct
import subprocess
import sys

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "dist_win32")
WORK_DIR = os.path.join(PROJECT_DIR, "build_win32")


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


def build():
    if struct.calcsize("P") != 4:
        raise RuntimeError(
            "Build with Python 3.10 32-bit. The resulting x86 app also runs on 64-bit Windows."
        )
    if sys.version_info[:2] != (3, 10):
        raise RuntimeError(
            f"Use Python 3.10 32-bit for RapidOCR x86; found Python {sys.version.split()[0]}."
        )

    print("[Windows x86 build] Installing pinned, prebuilt project dependencies.", flush=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--only-binary=:all:",
            "-r",
            os.path.join(PROJECT_DIR, "requirements.txt"),
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
            os.path.join(PROJECT_DIR, "Librairie.spec"),
        ],
        cwd=PROJECT_DIR,
        check=True,
    )

    executable = os.path.join(OUTPUT_DIR, "Librairie.exe")
    if pe_machine(executable) != 0x014C:
        raise RuntimeError(f"PyInstaller produced a non-x86 executable: {executable}")
    print(f"[Windows x86 build] Ready to distribute: {executable}", flush=True)
    print(
        "[Windows x86 build] Users need no Python, OCR engine, models, or internet connection.",
        flush=True,
    )


if __name__ == "__main__":
    try:
        build()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"[Windows x86 build] ERROR: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
