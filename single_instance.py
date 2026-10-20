"""One app per Windows session; subsequent launches reopen its window."""
import ctypes
import threading
from ctypes import wintypes

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.SetEvent.argtypes = [wintypes.HANDLE]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


class SingleInstance:
    def __init__(self, name='Local\\WhisperFlow.Application.v1'):
        self._stopped = threading.Event()
        self._thread = None
        self._mutex = kernel32.CreateMutexW(None, False, name)
        already_exists = ctypes.get_last_error() == 183
        if not self._mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        self._event = kernel32.CreateEventW(None, False, False, name + '.Open')
        if not self._event:
            kernel32.CloseHandle(self._mutex)
            raise ctypes.WinError(ctypes.get_last_error())
        self.is_primary = not already_exists
        if already_exists:
            kernel32.SetEvent(self._event)

    def watch(self, callback):
        def run():
            while not self._stopped.is_set():
                if kernel32.WaitForSingleObject(self._event, 250) == 0:
                    if not self._stopped.is_set():
                        callback()
        self._thread = threading.Thread(target=run, daemon=True, name='WhisperFlowReopen')
        self._thread.start()

    def close(self):
        self._stopped.set()
        if self._thread:
            self._thread.join(timeout=1)
        kernel32.CloseHandle(self._event)
        kernel32.CloseHandle(self._mutex)
