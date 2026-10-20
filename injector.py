"""
WhisperFlow - Text Injector
Module d'injection textuelle ultra-rapide (< 1ms) dans la fenêtre active sous Windows.
Utilise l'API native Win32 SendInput (KEYEVENTF_UNICODE) en C-batch sans toucher au presse-papier.
"""

import ctypes
from ctypes import wintypes
import struct
import time
import win32clipboard

def copy_text(text):
    """Keep the transcription available for Ctrl+V, even without an editable field."""
    for attempt in range(5):
        opened = False
        try:
            win32clipboard.OpenClipboard()
            opened = True
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            return True
        except Exception:
            time.sleep(0.02)
        finally:
            if opened:
                win32clipboard.CloseClipboard()
    return False

# Constantes Win32
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_MENU = 0x12       # Alt
VK_SHIFT = 0x10
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_V = 0x56

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t)
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD)
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t)
    ]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT)
        ]
    _anonymous_ = ("_input",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", _INPUT)
    ]

user32 = ctypes.windll.user32
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

def release_held_modifiers():
    """
    Relâche préventivement les touches de modification (Ctrl, Win, Alt, Shift)
    si elles sont encore maintenues physiquement ou logiquement par le Push-to-Talk,
    afin d'éviter tout déclenchement accidentel de raccourcis système (ex: Ctrl+A, Ctrl+W).
    """
    modifiers = [VK_CONTROL, VK_LWIN, VK_RWIN, VK_MENU, VK_SHIFT]
    for vk in modifiers:
        if user32.GetAsyncKeyState(vk) & 0x8000:
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

class TextInjector:
    @staticmethod
    def inject(text):
        """
        Injecte le texte directement dans l'application active.
        Exécution atomique en un seul appel système SendInput C-array (< 1ms).
        Aucun conflit de presse-papier, aucune altération de l'historique utilisateur.
        """
        if not text or not text.strip():
            return 0

        # 1. Libérer les modificateurs éventuels (provenant du push-to-talk)
        release_held_modifiers()

        # 2. Conversion du texte en code units UTF-16 (gestion native des accents et emojis)
        raw_utf16 = text.encode('utf-16-le')
        unit_count = len(raw_utf16) // 2
        utf16_units = struct.unpack(f'<{unit_count}H', raw_utf16)

        events = []
        for unit in utf16_units:
            if unit == 0x000D:  # '\r' : ignoré
                continue
            elif unit == 0x000A:  # '\n' : Touche Entrée
                # KeyDown Enter
                kd = INPUT(type=INPUT_KEYBOARD)
                kd.ki = KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
                events.append(kd)
                # KeyUp Enter
                ku = INPUT(type=INPUT_KEYBOARD)
                ku.ki = KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
                events.append(ku)
            else:
                # KeyDown Unicode
                kd = INPUT(type=INPUT_KEYBOARD)
                kd.ki = KEYBDINPUT(wVk=0, wScan=unit, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
                events.append(kd)
                # KeyUp Unicode
                ku = INPUT(type=INPUT_KEYBOARD)
                ku.ki = KEYBDINPUT(wVk=0, wScan=unit, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
                events.append(ku)

        if not events:
            return 0

        # 3. Construction du C-Array contigu et envoi en un appel atomique
        total_events = len(events)
        input_array = (INPUT * total_events)(*events)
        sent = user32.SendInput(total_events, input_array, ctypes.sizeof(INPUT))
        return sent

    @staticmethod
    def paste(text):
        """Clipboard paste is accepted by more text fields than Unicode key events."""
        if not text or not text.strip():
            return 0
        if not copy_text(text):
            return TextInjector.inject(text)
        release_held_modifiers()
        events = (INPUT * 4)()
        for event, vk, flags in zip(events, (VK_CONTROL, VK_V, VK_V, VK_CONTROL),
                                   (0, 0, KEYEVENTF_KEYUP, KEYEVENTF_KEYUP)):
            event.type = INPUT_KEYBOARD
            event.ki = KEYBDINPUT(wVk=vk, dwFlags=flags)
        return user32.SendInput(4, events, ctypes.sizeof(INPUT))
