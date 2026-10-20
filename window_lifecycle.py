"""Hide the Windows form without waiting for WebView2 to finish loading."""
import ctypes
import logging
from ctypes import wintypes

user32 = ctypes.windll.user32
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


def hide_to_background(window):
    try:
        native = window.native
        if native is not None:
            user32.ShowWindow(native.Handle.ToInt64(), 0)
        elif window.events.shown.is_set():
            window.hide()
    except Exception:
        logging.exception('Masquage de la fenêtre impossible ; fermeture annulée')
    # The cancel result must survive any hide error, including during startup.
    return False


def close_native(window):
    native = window.native
    if native is not None:
        user32.PostMessageW(native.Handle.ToInt64(), 0x0010, 0, 0)


def show_native(window):
    native = window.native
    if native is not None:
        user32.ShowWindow(native.Handle.ToInt64(), 9)
