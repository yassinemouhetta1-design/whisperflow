"""Native Windows registration of Alt+comma for the last transcription."""
import ctypes
import logging
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL('user32', use_last_error=True)
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


class PasteHotkey:
    def __init__(self, callback):
        self._callback = callback
        self._ready = threading.Event()
        self._thread_id = None
        self.registered = False
        self._thread = threading.Thread(target=self._run, daemon=True, name='WhisperFlowPasteHotkey')
        self._thread.start()
        self._ready.wait(3)

    def _run(self):
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        self.registered = bool(user32.RegisterHotKey(None, 1, 0x4001, 0xBC))
        self._ready.set()
        if not self.registered:
            logging.error('Alt+, indisponible : erreur Windows %s', ctypes.get_last_error())
            return
        try:
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:
                    # Wait for the user's Alt release before generating Ctrl+V.
                    deadline = time.monotonic() + 0.5
                    while user32.GetAsyncKeyState(0x12) & 0x8000 and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self._callback()
        except Exception:
            logging.exception('Erreur du raccourci Alt+,')
        finally:
            user32.UnregisterHotKey(None, 1)

    def close(self):
        if self._thread_id and self.registered:
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
