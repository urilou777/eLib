# -*- mode: python ; coding: utf-8 -*-
import os
import struct
from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_all, collect_submodules

if struct.calcsize("P") != 4:
    raise RuntimeError("La version distribuée doit être construite avec Python Windows 32 bits.")

project_dir = os.path.abspath(SPECPATH)

# Les dossiers par défaut « dist/ » et « build/ » sont supprimés du projet :
# toute sortie doit passer par tools/build_windows_x86.py (--distpath dist_win32,
# --workpath build_win32). Un appel manuel « pyinstaller Librairie.spec » sans
# ces drapeaux est refusé pour ne pas recréer ces dossiers.
# WORKPATH n'est pas injecté par toutes les versions de PyInstaller : garde tolérante.
_distpath = globals().get("DISTPATH", "")
_workpath = globals().get("WORKPATH", "")
if _distpath and os.path.abspath(_distpath).lower() == os.path.join(project_dir, "dist").lower():
    raise RuntimeError("Dossier de sortie « dist/ » interdit : lancez tools/build_windows_x86.py (sortie dist_win32).")
if _workpath and os.path.abspath(_workpath).lower() == os.path.join(project_dir, "build").lower():
    raise RuntimeError("Dossier de travail « build/ » interdit : lancez tools/build_windows_x86.py (travail build_win32).")

webview_runtime_dir = os.path.join(
    project_dir,
    'build_win32',
    'webview2_runtime',
    'Microsoft.WebView2.FixedVersionRuntime.155.0.4283.62.x86',
)
if not os.path.isfile(os.path.join(webview_runtime_dir, 'msedgewebview2.exe')):
    raise RuntimeError("Bundled WebView2 Fixed Runtime is missing; run tools/build_windows_x86.py.")
rapid_datas, rapid_bins, rapid_hidden = collect_all('rapidocr_onnxruntime')
hook_dir = os.path.join(project_dir, 'tools', 'pyinstaller_hooks')
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
    hookspath=[hook_dir],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
a.datas += Tree(webview_runtime_dir, prefix='webview2')
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='eLib',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # upx désactivé : la décompression à chaque lancement dégrade le démarrage à froid
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_dir, 'app', 'static', 'app-icon.ico'),
)