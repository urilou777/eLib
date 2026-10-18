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
import threading
import time
import webbrowser

# Assure la détection du package app même avec un runtime Python portable
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import uvicorn

from app import security
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
    https_server, _ = start_https()

    try:
        if headless:
            print(f"Poste : {url}  |  Mobile : https port {security.state['https_port']}")
            while t.is_alive():
                time.sleep(1)
        else:
            import webview
            webview.create_window(
                "Librairi-E – Chrétienne et impactante",
                url,
                width=1280,
                height=760,
                min_size=(960, 580),
                maximized=True
            )
            webview.start()
    except KeyboardInterrupt:
        pass
    except Exception:
        webbrowser.open(url)
        try:
            while t.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        restore_sleep()
        server.should_exit = True
        if https_server:
            https_server.should_exit = True


if __name__ == "__main__":
    main()
