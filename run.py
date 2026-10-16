"""Lanceur : serveur local + fenêtre native (pywebview) ou navigateur en repli."""
import socket
import threading
import time
import webbrowser
import uvicorn
from app.main import app


def free_port(preferred=8765):
    for p in (preferred, 0):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            s.close()


def main():
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    try:
        import webview
        webview.create_window("Librairie – Gestion de stock", url, width=1400, height=900, min_size=(1000, 650))
        webview.start()
    except Exception:
        webbrowser.open(url)
        try:
            while t.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    server.should_exit = True


if __name__ == "__main__":
    main()
