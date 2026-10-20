import os
import sys
import json
import time
import threading
import logging
import queue
import ctypes
import winsound
from pynput import keyboard, mouse

# L'import de transcriber enregistre lui-même les DLL NVIDIA (cuBLAS, cuDNN)
# avant de charger ctranslate2.
from transcriber import WhisperTranscriber, app_base_dir
from recorder import AudioRecorder
from overlay import FloatingOverlay
from injector import TextInjector, copy_text
from paste_hotkey import PasteHotkey

def config_file_path():
    """
    Emplacement de la configuration :
    - config.json à côté de l'exécutable si présent (mode portable) ;
    - sinon %APPDATA%/WhisperFlow/config.json ( installation dans Program Files,
      non inscriptible sans élévation).
    """
    portable = os.path.join(app_base_dir(), "config.json")
    if os.path.exists(portable):
        return portable
    appdata = os.path.join(os.environ.get("APPDATA", app_base_dir()), "WhisperFlow")
    try:
        os.makedirs(appdata, exist_ok=True)
    except Exception:
        return portable
    return os.path.join(appdata, "config.json")

CONFIG_FILE = config_file_path()

DEFAULT_CONFIG = {
    "hotkey_push": "ctrl+win",
    "hotkey_toggle": "mouse5",
    "hotkey_cancel": "esc",
    "model_size": "large-v3-turbo",
    "device": "cuda",
    "compute_type": "float16",
    "language": "fr",
    "sound_feedback": False,
    "show_overlay": True,
    "beam_size": 1,
    "vad_filter": True
}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur écriture config : {e}")

class AppBackend:
    def __init__(self, overlay=None):
        self._ui_queue = queue.Queue()
        threading.Thread(target=self._ui_worker, name="WhisperFlowUIUpdates", daemon=True).start()
        self.config = load_config()
        self.config["show_overlay"] = True
        self._overlay = overlay if overlay is not None else FloatingOverlay()
        self._recorder = AudioRecorder(sample_rate=16000)
        self._window = None

        self._transcriber = None
        self.is_recording = False
        self.recording_mode = None  # "push" or "toggle"
        self.pressed_keys = set()
        self._lock = threading.Lock()
        self._processing_lock = threading.Lock()
        self._model_lock = threading.Lock()
        self._model_loading = True
        self._last_error = None
        self._closing = False
        self._target_hwnd = None
        self._last_transcript = ""
        self._paste_hotkey_down = False
        self._copilot_down = False

        # Démarrer le chargement de Whisper
        threading.Thread(target=self._init_whisper, daemon=True).start()

        # Démarrer l'écouteur global clavier avec filtre Win32 (interception Copilot VK_F23)
        self._listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
            win32_event_filter=self._win32_filter
        )
        self._listener.daemon = True
        self._listener.start()

        # Démarrer l'écouteur global souris (pour boutons latéraux XButton1/XButton2)
        self._mouse_listener = mouse.Listener(
            on_click=self._on_mouse_click,
            win32_event_filter=self._mouse_win32_filter
        )
        self._mouse_listener.daemon = True
        self._mouse_listener.start()
        self._paste_hotkey = PasteHotkey(self.paste_last_transcript)
        if not self._paste_hotkey.registered:
            self._last_error = "Alt+, est déjà utilisé par une autre application. Le bouton Copier reste disponible."

    def _notify_ui(self, script):
        # Never wait for WebView from a Windows keyboard/mouse hook.
        if self._window and not self._closing:
            self._ui_queue.put(script)

    def _ui_worker(self):
        while True:
            script = self._ui_queue.get()
            if script is None:
                return
            try:
                if self._window and not self._closing:
                    self._window.evaluate_js(script)
            except Exception:
                logging.debug("Notification UI indisponible", exc_info=True)

    def set_window(self, win):
        self._window = win

    def shutdown(self):
        """Arrêt propre : écouteurs globaux, overlay, micro. Appelé à la fermeture réelle."""
        self._closing = True
        self._ui_queue.put(None)
        self._paste_hotkey.close()
        for listener in (self._listener, self._mouse_listener):
            try:
                listener.stop()
            except Exception:
                pass
        if self._overlay:
            try:
                self._overlay.close()
            except Exception:
                pass
            self._overlay = None
        try:
            self._recorder.close()
        except Exception:
            pass

    def _init_whisper(self):
        with self._model_lock:
            self._model_loading = True
            try:
                with self._processing_lock:
                    self._transcriber = None
                    self._transcriber = WhisperTranscriber(
                        model_size=self.config["model_size"],
                        device=self.config.get("device", "cuda"),
                        compute_type=self.config.get("compute_type", "float16")
                    )
                self._last_error = None
            except Exception as e:
                self._report_error("Chargement du modèle impossible", e)
            finally:
                self._model_loading = False

    def _report_error(self, message, error=None):
        self._last_error = message + (f" : {error}" if error else "")
        logging.error(self._last_error, exc_info=error is not None)
        if self._window and not self._closing:
            try:
                self._notify_ui(
                    f"if (window.onAppError) window.onAppError({json.dumps(self._last_error)});")
            except Exception:
                logging.debug("Fenêtre indisponible pour notification", exc_info=True)

    def get_status(self):
        return {
            "model_ready": self._transcriber is not None and not self._model_loading,
            "error": self._last_error,
            "model_size": self.config.get("model_size", "large-v3-turbo"),
            "device": self._transcriber.device if self._transcriber else self.config.get("device", "cuda"),
            "recording": self.is_recording
        }

    # --- API Exposée au JavaScript ---
    def get_config(self):
        return self.config

    def paste_last_transcript(self):
        text = self._last_transcript
        if not text:
            self._report_error("Aucune transcription à coller pour le moment.")
            return {"status": "empty"}
        try:
            sent = TextInjector.paste(text)
            return {"status": "ok" if sent == 4 else "error"}
        except Exception as e:
            self._report_error("Collage impossible", e)
            return {"status": "error"}

    def set_key(self, action, key_name):
        key_name = key_name.lower().strip()
        if action == "push_to_talk":
            self.config["hotkey_push"] = key_name
        elif action == "toggle":
            self.config["hotkey_toggle"] = key_name
        elif action == "cancel":
            self.config["hotkey_cancel"] = key_name
        save_config(self.config)
        return {"status": "ok", "action": action, "key": key_name}

    def set_setting(self, key, value):
        if key == "show_overlay":
            value = True
        self.config[key] = value
        save_config(self.config)
        if key == "model_size":
            self._model_loading = True
            threading.Thread(target=self._init_whisper, daemon=True).start()
        elif key == "show_overlay":
            if not self._overlay:
                self._overlay = FloatingOverlay()
            self._overlay.ensure_visible()
        return {"status": "ok"}

    def start_test_record(self):
        started = self.start_recording(mode="test")
        return {"status": "recording" if started else "error", "error": self._last_error}

    def stop_test_record(self):
        try:
            with self._processing_lock:
                return self._stop_test_record()
        except Exception as e:
            self._report_error("Transcription impossible", e)
            return {"text": "", "duration": 0, "error": self._last_error}
        finally:
            if self._overlay:
                self._overlay.hide()

    def _stop_test_record(self):
        t0 = time.time()
        audio = self.stop_recording()
        if len(audio) < 16000 * 0.3:
            if self._window:
                try:
                    self._notify_ui("if (window.onRecordingStateChange) window.onRecordingStateChange(false, 'idle');")
                except Exception:
                    pass
            return {"text": "", "duration": 0}

        text = ""
        if self._transcriber:
            text = self._transcriber.transcribe(
                audio,
                language=self.config.get("language", "fr"),
                beam_size=self.config.get("beam_size", 1),
                vad_filter=self.config.get("vad_filter", True)
            )
        duration = time.time() - t0
        if text:
            self._last_transcript = text
        if self._window:
            try:
                self._notify_ui(f"if (window.onRecordingStateChange) window.onRecordingStateChange(false, 'done', {duration});")
            except Exception:
                pass
        return {"text": text, "duration": duration}

    # --- Enregistrement et Transcription ---
    def _play_sound(self, freq, dur):
        if self.config.get("sound_feedback", False):
            try:
                winsound.Beep(freq, dur)
            except Exception:
                pass

    def start_recording(self, mode="push"):
        with self._lock:
            if self.is_recording or self._closing:
                return False
            if self._model_loading or self._transcriber is None:
                self._report_error("Le modèle vocal n'est pas prêt")
                return False
            try:
                self._recorder.start()
            except Exception as e:
                self._report_error("Microphone indisponible", e)
                return False
            self.is_recording = True
            self.recording_mode = mode
            self._last_error = None
            self._target_hwnd = ctypes.windll.user32.GetForegroundWindow()

        logging.info("Dictée démarrée (%s), cible=%s", mode, self._target_hwnd)
        if self.config.get("sound_feedback", False):
            threading.Thread(target=self._play_sound, args=(1000, 70), daemon=True).start()
        if self._overlay and mode != "test":
            self._overlay.show_recording()

        if self._window:
            try:
                self._notify_ui(f"if (window.onRecordingStateChange) window.onRecordingStateChange(true, '{mode}');")
            except Exception:
                pass
        return True

    def stop_recording(self):
        with self._lock:
            if not self.is_recording:
                return []
            self.is_recording = False
            self.recording_mode = None
            audio = self._recorder.stop()
        logging.info("Dictée arrêtée, %s échantillons", len(audio))

        if self.config.get("sound_feedback", False):
            threading.Thread(target=self._play_sound, args=(800, 70), daemon=True).start()
        if self._overlay:
            self._overlay.show_transcribing()

        if self._window:
            try:
                self._notify_ui("if (window.onRecordingStateChange) window.onRecordingStateChange('transcribing');")
            except Exception:
                pass

        return audio

    def cancel_recording(self):
        with self._lock:
            if not self.is_recording:
                return
            self.is_recording = False
            self.recording_mode = None
            self._recorder.cancel()
        if self._overlay:
            self._overlay.hide()
        if self.config.get("sound_feedback", False):
            threading.Thread(target=self._play_sound, args=(400, 100), daemon=True).start()

        if self._window:
            try:
                self._notify_ui("if (window.onRecordingStateChange) window.onRecordingStateChange(false, 'cancel');")
            except Exception:
                pass

    def _process_and_inject(self, audio, target_hwnd=None):
        if target_hwnd is None:
            target_hwnd = self._target_hwnd
        try:
            with self._processing_lock:
                if not self._closing:
                    self._process_audio(audio, target_hwnd)
        except Exception as e:
            self._report_error("Transcription impossible", e)
        finally:
            if self._overlay:
                self._overlay.hide()

    def _process_audio(self, audio, target_hwnd):
        if len(audio) < 16000 * 0.3:
            if self._overlay:
                self._overlay.hide()
            if self._window:
                try:
                    self._notify_ui("if (window.onRecordingStateChange) window.onRecordingStateChange(false, 'idle');")
                except Exception:
                    pass
            return

        t0 = time.time()
        text = ""
        if self._transcriber:
            text = self._transcriber.transcribe(
                audio,
                language=self.config.get("language", "fr"),
                beam_size=self.config.get("beam_size", 1),
                vad_filter=self.config.get("vad_filter", True)
            )
        dt = time.time() - t0
        if text:
            self._last_transcript = text

        if self._overlay:
            self._overlay.hide()

        # Notification au frontend s'il est ouvert
        if self._window:
            try:
                js_code = f"if (window.onGlobalTranscription) window.onGlobalTranscription({json.dumps(text)}, {dt});"
                self._notify_ui(js_code)
                self._notify_ui(f"if (window.onRecordingStateChange) window.onRecordingStateChange(false, 'done', {dt});")
            except Exception:
                pass

        if text:
            if self._closing:
                return
            if ctypes.windll.user32.GetForegroundWindow() != target_hwnd:
                copied = copy_text(text)
                self._report_error("La fenêtre active a changé. " +
                    ("Texte copié : faites Ctrl+V dans votre champ." if copied else "Le texte est disponible dans le Studio."))
                return
            sent = TextInjector.paste(text)
            if sent != 4:
                self._report_error("Insertion du texte incomplète. Le texte est disponible dans le Studio et, si la copie a réussi, avec Ctrl+V.")

    # --- Filtre Win32 pour interception de la touche matérielle Copilot ---
    def _win32_filter(self, msg, data):
        # 0x86 est VK_F23 (le signal matériel envoyé par la touche physique Copilot sous Windows 11)
        if data.vkCode == 0x86:
            target_push = self.config.get("hotkey_push", "").lower().strip()
            target_toggle = self.config.get("hotkey_toggle", "").lower().strip()
            is_copilot_target = any(t in ("copilot", "f23") for t in (target_push, target_toggle))

            if is_copilot_target:
                # Appui (WM_KEYDOWN 0x0100 ou WM_SYSKEYDOWN 0x0104)
                if msg in (0x0100, 0x0104):
                    if self._copilot_down:
                        self._listener.suppress_event()
                        return False
                    self._copilot_down = True
                    if target_push in ("copilot", "f23"):
                        if not self.is_recording:
                            self.start_recording(mode="push")
                    elif target_toggle in ("copilot", "f23"):
                        if not self.is_recording:
                            self.start_recording(mode="toggle")
                        elif self.recording_mode == "toggle":
                            audio = self.stop_recording()
                            threading.Thread(target=self._process_and_inject, args=(audio,), daemon=True).start()
                    # Retourne False pour intercepter et SUPPRIMER la touche : Windows n'ouvrira JAMAIS Copilot ni ChatGPT !
                    self._listener.suppress_event()
                    return False

                # Relâchement (WM_KEYUP 0x0101 ou WM_SYSKEYUP 0x0105)
                elif msg in (0x0101, 0x0105):
                    self._copilot_down = False
                    if target_push in ("copilot", "f23") and self.is_recording and self.recording_mode == "push":
                        audio = self.stop_recording()
                        threading.Thread(target=self._process_and_inject, args=(audio,), daemon=True).start()
                    self._listener.suppress_event()
                    return False
        return True

    # --- Filtre Win32 pour boutons latéraux de souris (XButton1/Mouse4 et XButton2/Mouse5) ---
    def _mouse_win32_filter(self, msg, data):
        # 0x020B = WM_XBUTTONDOWN, 0x020C = WM_XBUTTONUP
        if msg in (0x020B, 0x020C):
            btn_idx = (data.mouseData >> 16) & 0xFFFF
            btn_name = "mouse4" if btn_idx == 1 else ("mouse5" if btn_idx == 2 else "")
            target_push = self.config.get("hotkey_push", "").lower().strip()
            target_toggle = self.config.get("hotkey_toggle", "").lower().strip()

            is_mouse_target = btn_name and (
                target_push in (btn_name, f"x{btn_idx}", f"souris{btn_idx + 3}") or
                target_toggle in (btn_name, f"x{btn_idx}", f"souris{btn_idx + 3}")
            )

            if is_mouse_target:
                # Événement clic enfoncé
                if msg == 0x020B:
                    if target_push in (btn_name, f"x{btn_idx}", f"souris{btn_idx + 3}"):
                        if not self.is_recording:
                            self.start_recording(mode="push")
                    elif target_toggle in (btn_name, f"x{btn_idx}", f"souris{btn_idx + 3}"):
                        if not self.is_recording:
                            self.start_recording(mode="toggle")
                        elif self.recording_mode == "toggle":
                            audio = self.stop_recording()
                            threading.Thread(target=self._process_and_inject, args=(audio,), daemon=True).start()
                    self._mouse_listener.suppress_event()
                    return False

                # Événement clic relâché
                elif msg == 0x020C:
                    if target_push in (btn_name, f"x{btn_idx}", f"souris{btn_idx + 3}") and self.is_recording and self.recording_mode == "push":
                        audio = self.stop_recording()
                        threading.Thread(target=self._process_and_inject, args=(audio,), daemon=True).start()
                    self._mouse_listener.suppress_event()
                    return False
        return True

    def _on_mouse_click(self, x, y, button, pressed):
        b_name = getattr(button, 'name', '')
        mapping = {"x1": "mouse4", "x2": "mouse5", "middle": "mouse3"}
        normalized = mapping.get(b_name, b_name)

        target_push = self.config.get("hotkey_push", "").lower().strip()
        target_toggle = self.config.get("hotkey_toggle", "").lower().strip()
        target_cancel = self.config.get("hotkey_cancel", "").lower().strip()

        # Annuler
        if pressed and target_cancel in (normalized, b_name, f"souris_{b_name}"):
            if self.is_recording:
                self.cancel_recording()
                return

        # Push-to-Talk pour boutons normaux sans filtre
        if target_push in (normalized, b_name, f"souris_{b_name}") and b_name not in ("x1", "x2"):
            if pressed:
                if not self.is_recording:
                    self.start_recording(mode="push")
            else:
                if self.is_recording and self.recording_mode == "push":
                    audio = self.stop_recording()
                    threading.Thread(target=self._process_and_inject, args=(audio,), daemon=True).start()
            return

        # Toggle pour boutons normaux sans filtre
        if target_toggle in (normalized, b_name, f"souris_{b_name}") and b_name not in ("x1", "x2") and pressed:
            if not self.is_recording:
                self.start_recording(mode="toggle")
            elif self.recording_mode == "toggle":
                audio = self.stop_recording()
                threading.Thread(target=self._process_and_inject, args=(audio,), daemon=True).start()

    # --- Gestionnaire de Raccourcis Globaux Clavier ---
    def _matches(self, key, target_name):
        if not target_name:
            return False
        k_str = ""
        if isinstance(key, keyboard.Key):
            k_str = key.name.lower()
        elif hasattr(key, 'char') and key.char:
            k_str = key.char.lower()

        target = target_name.lower().strip()
        if target in ("copilot", "f23"):
            return k_str in ("copilot", "f23") or key == getattr(keyboard.Key, "f23", None)

        if target in ("ctrl+win", "win+ctrl"):
            has_ctrl = any(k in self.pressed_keys for k in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl])
            has_win = any(k in self.pressed_keys for k in [keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r])
            return has_ctrl and has_win

        return k_str == target

    def _on_key_press(self, key):
        if key in self.pressed_keys:
            return
        self.pressed_keys.add(key)

        # 1. Annuler
        if self._matches(key, self.config.get("hotkey_cancel", "esc")):
            if self.is_recording:
                self.cancel_recording()
                return

        # 2. Push-to-Talk
        if self._matches(key, self.config.get("hotkey_push", "f8")):
            if not self.is_recording:
                self.start_recording(mode="push")
            return

        # 3. Toggle
        if self._matches(key, self.config.get("hotkey_toggle", "f9")):
            if not self.is_recording:
                self.start_recording(mode="toggle")
            elif self.recording_mode == "toggle":
                audio = self.stop_recording()
                threading.Thread(target=self._process_and_inject, args=(audio,), daemon=True).start()

    def _on_key_release(self, key):
        # Push-to-talk release
        target_push = self.config.get("hotkey_push", "f8").lower()
        if self.is_recording and self.recording_mode == "push":
            if target_push in ("ctrl+win", "win+ctrl"):
                if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
                    audio = self.stop_recording()
                    threading.Thread(target=self._process_and_inject, args=(audio,), daemon=True).start()
            else:
                k_str = key.name.lower() if isinstance(key, keyboard.Key) else (key.char.lower() if hasattr(key, 'char') and key.char else "")
                if k_str == target_push:
                    audio = self.stop_recording()
                    threading.Thread(target=self._process_and_inject, args=(audio,), daemon=True).start()

        self.pressed_keys.discard(key)
