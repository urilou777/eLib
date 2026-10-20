# -*- mode: python ; coding: utf-8 -*-
import os
import struct
from PyInstaller.utils.hooks import collect_all, collect_submodules

if struct.calcsize("P") != 4:
    raise RuntimeError("La version distribuée doit être construite avec Python Windows 32 bits.")

project_dir = os.path.abspath(SPECPATH)
rapid_datas, rapid_bins, rapid_hidden = collect_all('rapidocr_onnxruntime')
hiddenimports = [
    'webview',
    'cryptography',
    'segno',
    'numpy',
    'onnxruntime',
    'cv2',
    'rapidocr_onnxruntime',
] + rapid_hidden
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('cryptography')

a = Analysis(
    ['run.py'],
    pathex=[project_dir],
    binaries=rapid_bins,
    datas=[('app/static', 'app/static')] + rapid_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Librairie',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)