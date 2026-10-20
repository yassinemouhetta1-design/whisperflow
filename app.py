import os
import sys
import logging
import threading
from logging.handlers import RotatingFileHandler

log_dir = os.path.join(os.environ.get('APPDATA', os.path.dirname(__file__)), 'WhisperFlow')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(
    os.path.join(log_dir, 'app.log'), maxBytes=2_000_000, backupCount=2, encoding='utf-8')])
sys.excepthook = lambda typ, value, tb: logging.critical('Erreur application', exc_info=(typ, value, tb))
threading.excepthook = lambda args: logging.error('Erreur thread %s', args.thread.name,
    exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

# Rediriger stdout/stderr si exécuté sous pythonw sans console
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# Enregistrer l'identifiant d'application pour Windows (icône Taskbar indépendante)
if sys.platform == "win32":
    import ctypes
    try:
        myappid = "WhisperFlow.Local.Dictation"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

from single_instance import SingleInstance

def resource_dir():
    """Dossier des ressources embarquées (frontend, assets) : _MEIPASS si gelé."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def run_app(instance, overlay):
    import webview
    from window_lifecycle import hide_to_background, close_native, show_native
    from backend import AppBackend
    from tray import TrayIcon
    base_dir = resource_dir()
    icon_path = os.path.join(base_dir, "assets", "icon.ico")
    if not os.path.exists(icon_path):
        icon_path = None

    backend = AppBackend(overlay=overlay)
    index_path = os.path.join(base_dir, "frontend", "index.html")

    window = webview.create_window(
        title="WhisperFlow",
        url=index_path,
        js_api=backend,
        width=920,
        height=720,
        min_size=(800, 620),
        background_color="#f5f5f7"
    )
    backend.set_window(window)

    # ---------------------------------------------------------------
    # Fermer la fenêtre ≠ quitter : réduction vers la zone de
    # notification, la dictée reste active en arrière-plan.
    # ---------------------------------------------------------------
    state = {"quitting": False, "hint_shown": False}
    quit_requested = threading.Event()

    def on_open():
        overlay.ensure_visible()
        show_native(window)

    def on_quit():
        logging.info("Arrêt explicite via Quitter WhisperFlow")
        state["quitting"] = True
        quit_requested.set()
        backend.shutdown()
        close_native(window)

    def on_closing():
        if state["quitting"]:
            return None  # quittage réel : laisse la fenêtre se fermer
        hide_to_background(window)
        overlay.ensure_visible()
        logging.info("Fenêtre masquée : dictée conservée en arrière-plan")
        if not state["hint_shown"]:
            state["hint_shown"] = True
            tray.notify_background()
        return False  # annule la fermeture : l'app reste en vie

    tray = TrayIcon(icon_path, on_open=on_open, on_quit=on_quit)
    tray.start()
    window.events.closing += on_closing
    instance.watch(on_open)

    try:
        try:
            webview.start(debug=False, icon=icon_path)
        except Exception:
            logging.exception("Interface indisponible ; dictée et jauge conservées")
        if not state["quitting"]:
            logging.warning("Interface arrêtée sans demande de quitter ; maintien en arrière-plan")
            quit_requested.wait()
    finally:
        backend.shutdown()
        tray.stop()

def main():
    if '--self-test' in sys.argv:
        from release_check import run_self_test
        raise SystemExit(run_self_test(sys.argv[1:]))
    instance = SingleInstance()
    try:
        if instance.is_primary:
            from overlay import FloatingOverlay
            overlay = FloatingOverlay()
            try:
                run_app(instance, overlay)
            finally:
                overlay.close()
    finally:
        instance.close()

if __name__ == "__main__":
    main()
