"""Lanceur : serveur local + fenêtre native (pywebview) ou navigateur en repli.

Deux écoutes distinctes (principe du moindre privilège réseau) :
- HTTP  sur 127.0.0.1 uniquement : le poste de caisse (jamais exposé au réseau) ;
- HTTPS sur le réseau local     : uniquement pour les téléphones appairés (scanner mobile).
Option --headless : serveur seul, sans fenêtre (utile pour tests / démarrage automatique).
"""
import ctypes
import os
import socket
import sys
import subprocess
import threading
import time
import webbrowser

# Assure la détection du package app même avec un runtime Python portable
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import uvicorn

from app import db, security
from app.main import app

# Constantes Windows pour empêcher la mise en veille du système pendant l'activité de caisse
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040


def configure_low_spec_hardware():
    """Optimise le rendu et la consommation mémoire/CPU sur machines modestes (Xeon, PC de caisse)."""
    if sys.platform == "win32":
        # Empêche WebView2 de saturer le CPU/GPU logiciel ou de crasher sur de vieux pilotes graphiques
        # --disable-features=Translate : désactive la traduction Chromium inutile
        # --disable-background-networking : coupe les requêtes réseau internes Edge
        # --disable-sync : coupe toute tentative de synchro Edge
        # --disable-component-update : bloque les màj de composants Edge en tâche de fond
        current_args = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
        opt_flags = "--disable-features=Translate --disable-background-networking --disable-sync --disable-component-update"
        if opt_flags not in current_args:
            os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"{current_args} {opt_flags}".strip()


def enable_high_dpi():
    """Active la netteté native haute résolution (Per-Monitor V2) pour éviter le flou de mise à l'échelle Windows."""
    if sys.platform == "win32":
        try:
            # Windows 10 1703+ : DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (-4)
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                # Windows 8.1+ : PROCESS_PER_MONITOR_DPI_AWARE (2)
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    # Windows Vista/7/8 : PROCESS_SYSTEM_DPI_AWARE (1)
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass


def prevent_sleep():
    """Empêche Windows de mettre le processeur et le réseau en veille automatique."""
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
            )
        except Exception:
            pass


def restore_sleep():
    """Restaure le comportement normal de mise en veille à la fermeture."""
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception:
            pass


def configure_webview_runtime():
    import webview

    if not getattr(sys, "frozen", False):
        return webview

    runtime_dir = os.path.join(sys._MEIPASS, "webview2")
    if not os.path.isfile(os.path.join(runtime_dir, "msedgewebview2.exe")):
        raise RuntimeError(f"The bundled WebView2 runtime is missing: {runtime_dir}")

    webview.settings["WEBVIEW2_RUNTIME_PATH"] = runtime_dir

    windows_version = sys.getwindowsversion()
    if windows_version.major == 10 and windows_version.build < 22000:
        for package_sid in ("*S-1-15-2-2:(OI)(CI)(RX)", "*S-1-15-2-1:(OI)(CI)(RX)"):
            result = subprocess.run(
                ["icacls.exe", runtime_dir, "/grant", package_sid],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(
                    "Could not set required WebView2 runtime permissions: "
                    f"{result.stderr.strip() or result.stdout.strip()}"
                )

    return webview


HTTPS_PREFERRED = 8766
TLS_CIPHERS = "ECDHE+AESGCM:ECDHE+CHACHA20"   # TLS 1.3 reste actif ; TLS 1.2 limité aux suites AEAD à confidentialité persistante


def free_port(preferred=8765, host="127.0.0.1"):
    for p in (preferred, 0):
        s = socket.socket()
        try:
            s.bind((host, p))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            s.close()


def wait_port(port, tries=100):
    for _ in range(tries):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


def start_https():
    """Démarre l'écoute HTTPS LAN si la PKI locale est disponible. Retourne (server, thread) ou (None, None)."""
    try:
        from app import certs
        ips = security.local_ips()
        cert, key = certs.ensure_server_cert(ips)
        port = free_port(HTTPS_PREFERRED, "0.0.0.0")
        cfg = uvicorn.Config(app, host="0.0.0.0", port=port, ssl_certfile=cert, ssl_keyfile=key,
                             ssl_ciphers=TLS_CIPHERS, log_config=None, server_header=False)
        srv = uvicorn.Server(cfg)
        th = threading.Thread(target=srv.run, daemon=True)
        th.start()
        if wait_port(port):
            security.state["https_port"] = port
            return srv, th
        srv.should_exit = True
    except Exception as e:      # le poste de caisse doit démarrer quoi qu'il arrive
        print(f"[mobile] HTTPS indisponible : {e}", file=sys.stderr)
    return None, None


def main():
    t0 = time.perf_counter()

    def phase(label):
        print(f"[perf] {label}: {time.perf_counter() - t0:.2f}s", file=sys.stderr)

    configure_low_spec_hardware()
    enable_high_dpi()
    prevent_sleep()
    headless = "--headless" in sys.argv
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, server_header=False))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    wait_port(port)
    phase("serveur HTTP prêt")

    https_holder = {}
    if headless:
        # Sans fenêtre, l'URL mobile doit être affichée dès le départ : HTTPS synchrone.
        srv, _ = start_https()
        if srv:
            https_holder["server"] = srv
        phase("HTTPS prêt (synchrone, mode headless)")
    else:
        # La fenêtre ne doit pas attendre la PKI : génération de certificat et
        # second uvicorn démarrent en parallèle, sans bloquer la peinture.
        def _https_bg():
            srv, _ = start_https()
            if srv:
                https_holder["server"] = srv
        threading.Thread(target=_https_bg, daemon=True).start()

    try:
        if headless:
            print(f"Poste : {url}  |  Mobile : https port {security.state['https_port']}")
            while t.is_alive():
                time.sleep(1)
        else:
            webview = configure_webview_runtime()
            window = webview.create_window(
                "eLib – Chrétienne et impactante",
                url,
                width=1280,
                height=760,
                min_size=(960, 580),
                maximized=True
            )
            if getattr(sys, "frozen", False) and sys.platform == "win32":
                from app.updater import start_update_monitor

                start_update_monitor(sys.executable, db.DATA_DIR, window)
            static_dir = os.path.join(
                getattr(sys, "_MEIPASS", _ROOT),
                "app",
                "static",
            )
            window_icon = os.path.join(static_dir, "favicon.ico")
            if not os.path.isfile(window_icon):
                raise FileNotFoundError(f"The desktop window icon is missing: {window_icon}")
            phase("lancement de la fenêtre")
            webview.start(icon=window_icon)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        if getattr(sys, "frozen", False):
            # Le binaire distribué n'a pas de console : journaliser la trace complète
            # à côté de l'exécutable pour diagnostiquer les échecs de démarrage.
            try:
                import traceback

                crash_log = os.path.join(os.path.dirname(sys.executable), "startup_crash.log")
                with open(crash_log, "a", encoding="utf-8") as fh:
                    fh.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                    fh.write(traceback.format_exc())
            except Exception:
                pass
            message = (
                "eLib could not start its bundled application window.\n\n"
                f"Details: {error}\n\n"
                "La trace complète est enregistrée dans startup_crash.log à côté de eLib.exe."
            )
            if sys.platform == "win32":
                ctypes.windll.user32.MessageBoxW(None, message, "eLib startup error", 0x10)
            else:
                print(message, file=sys.stderr)
        else:
            webbrowser.open(url)
            try:
                while t.is_alive():
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
    finally:
        restore_sleep()
        server.should_exit = True
        if https_holder.get("server"):
            https_holder["server"].should_exit = True


if __name__ == "__main__":
    main()
