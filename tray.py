"""
WhisperFlow - Icône de la zone de notification (barre d'état système).

Comportement « Wispr Flow » : fermer la fenêtre ne quitte pas l'application,
la dictée reste active en arrière-plan. Cette icône permet de rouvrir la
fenêtre (clic gauche) ou de quitter réellement (clic droit → Quitter).

Implémentation : pywin32 pour la fenêtre de messages + ctypes pour
Shell_NotifyIconW (affichage de l'icône et de la notification).
Aucune dépendance supplémentaire.
"""

import ctypes
import logging
import threading
from ctypes import wintypes

import win32api
import win32con
import win32gui

logger = logging.getLogger(__name__)

# --- Constantes Shell_NotifyIcon ---
NIM_ADD = 0x00
NIM_MODIFY = 0x01
NIM_DELETE = 0x02

NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
NIF_INFO = 0x10

NIIF_INFO = 0x01

WM_APP_TRAY = win32con.WM_APP + 1
WM_APP_OPEN = win32con.WM_APP + 2
WM_APP_QUIT = win32con.WM_APP + 3
WM_APP_BALLOON = win32con.WM_APP + 4

ID_TRAY = 1
CMD_OPEN = 1001
CMD_QUIT = 1002

_taskbar_created_msg = win32gui.RegisterWindowMessage("TaskbarCreated")


class NOTIFYICONDATAW(ctypes.Structure):
    """Structure V2 (sans GUID) : cbSize = sizeof exactly, reconnu par Windows."""
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]


_shell32 = ctypes.windll.shell32
_shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
_shell32.Shell_NotifyIconW.restype = wintypes.BOOL


class TrayIcon:
    """
    Icône système WhisperFlow.
    - Clic gauche : rouvre la fenêtre (callback on_open).
    - Clic droit : menu « Ouvrir / Quitter » (callbacks on_open / on_quit).
    - notify_background() : bulle d'information unique « app active en arrière-plan ».
    Tout tourne dans un thread démon avec sa propre boucle de messages Win32.
    """

    def __init__(self, icon_path=None, on_open=None, on_quit=None):
        self.icon_path = icon_path
        self.on_open = on_open or (lambda: None)
        self.on_quit = on_quit or (lambda: None)
        self._hwnd = None
        self._hicon = None
        self._thread = None
        self._ready = threading.Event()

    # --- API publique (appelable depuis n'importe quel thread) ---

    def start(self):
        self._thread = threading.Thread(target=self._run, name="WhisperFlowTray", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def notify_background(self):
        """Bulle : « WhisperFlow continue de tourner en arrière-plan »."""
        if self._hwnd:
            win32gui.PostMessage(self._hwnd, WM_APP_BALLOON, 0, 0)

    def stop(self):
        if self._hwnd:
            win32gui.PostMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)

    # --- Interne : thread de la barre d'état ---

    def _run(self):
        try:
            self._create_window()
            self._ready.set()
            win32gui.PumpMessages()
        except Exception as e:
            logger.warning("Icône tray indisponible : %s", e)
            self._ready.set()

    def _create_window(self):
        wc = win32gui.WNDCLASS()
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = "WhisperFlowTrayWnd"
        wc.lpfnWndProc = self._wnd_proc
        if self.icon_path:
            try:
                wc.hIcon = win32gui.LoadImage(
                    0, self.icon_path, win32con.IMAGE_ICON, 0, 0,
                    win32con.LR_DEFAULTSIZE | win32con.LR_LOADFROMFILE,
                )
            except Exception:
                wc.hIcon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
        else:
            wc.hIcon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
        win32gui.RegisterClass(wc)
        self._hicon = wc.hIcon

        self._hwnd = win32gui.CreateWindow(
            wc.lpszClassName,
            "WhisperFlow",
            win32con.WS_OVERLAPPED,
            0, 0, 0, 0,
            None, None, wc.hInstance, None,
        )
        self._add_icon()

    def _make_nid(self, flags):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = ID_TRAY
        nid.uFlags = flags
        nid.uCallbackMessage = WM_APP_TRAY
        nid.hIcon = self._hicon
        nid.szTip = "WhisperFlow — dictée vocale active"
        return nid

    def _add_icon(self):
        nid = self._make_nid(NIF_MESSAGE | NIF_ICON | NIF_TIP)
        _shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    def _show_balloon(self):
        nid = self._make_nid(NIF_INFO)
        nid.szInfo = (
            "WhisperFlow continue de tourner en arrière-plan : la dictée reste active.\n"
            "Cliquez sur cette icône pour rouvrir la fenêtre."
        )
        nid.szInfoTitle = "WhisperFlow en arrière-plan"
        nid.dwInfoFlags = NIIF_INFO
        _shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        # Retire l'état « bulle » après affichage pour garder l'icône normale
        nid = self._make_nid(NIF_MESSAGE | NIF_ICON | NIF_TIP)
        _shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _remove_icon(self):
        nid = self._make_nid(0)
        _shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

    def _show_menu(self):
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, CMD_OPEN, "Ouvrir WhisperFlow")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, CMD_QUIT, "Quitter WhisperFlow")
        try:
            # SetForegroundWindow requis pour que le menu se referme correctement
            win32gui.SetForegroundWindow(self._hwnd)
            x, y = win32api.GetCursorPos()
            cmd = win32gui.TrackPopupMenu(
                menu,
                win32con.TPM_RETURNCMD | win32con.TPM_RIGHTBUTTON | win32con.TPM_NONOTIFY,
                x, y, 0, self._hwnd, None,
            )
        finally:
            win32gui.DestroyMenu(menu)
        if cmd == CMD_OPEN:
            win32gui.PostMessage(self._hwnd, WM_APP_OPEN, 0, 0)
        elif cmd == CMD_QUIT:
            win32gui.PostMessage(self._hwnd, WM_APP_QUIT, 0, 0)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_APP_TRAY:
                event = lparam & 0xFFFF
                if event == win32con.WM_LBUTTONUP or event == win32con.WM_LBUTTONDBLCLK:
                    win32gui.PostMessage(hwnd, WM_APP_OPEN, 0, 0)
                elif event == win32con.WM_RBUTTONUP:
                    self._show_menu()
                return 0
            if msg == WM_APP_OPEN:
                try:
                    self.on_open()
                except Exception as e:
                    logger.error("on_open : %s", e)
                return 0
            if msg == WM_APP_QUIT:
                try:
                    self.on_quit()
                except Exception as e:
                    logger.error("on_quit : %s", e)
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                return 0
            if msg == WM_APP_BALLOON:
                self._show_balloon()
                return 0
            if msg == _taskbar_created_msg:
                # Recrée l'icône après un redémarrage de l'Explorateur
                self._add_icon()
                return 0
            if msg == win32con.WM_CLOSE:
                self._remove_icon()
                win32gui.DestroyWindow(hwnd)
                return 0
            if msg == win32con.WM_DESTROY:
                self._hwnd = None
                win32gui.PostQuitMessage(0)
                return 0
        except Exception as e:
            logger.warning("Tray wndproc : %s", e)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
