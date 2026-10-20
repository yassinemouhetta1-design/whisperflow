"""Regression checks without opening the microphone or injecting keyboard input."""
import os
import subprocess
import sys
import threading
import unittest
import queue
from unittest.mock import patch, Mock, MagicMock
import numpy as np

from recorder import AudioRecorder
from transcriber import WhisperTranscriber
from single_instance import SingleInstance
from tray import TrayIcon
from backend import AppBackend
from injector import TextInjector, copy_text, KEYEVENTF_KEYUP
from paste_hotkey import PasteHotkey
from overlay import FloatingOverlay
from window_lifecycle import hide_to_background


class Regressions(unittest.TestCase):
    def test_unexpected_ui_exit_keeps_backend_until_explicit_quit(self):
        import app
        fake_webview = MagicMock()
        fake_window = fake_webview.create_window.return_value
        backend, tray = Mock(), Mock()
        quit_event = Mock()
        with patch.dict(sys.modules, {'webview': fake_webview}), \
             patch('backend.AppBackend', return_value=backend), \
             patch('tray.TrayIcon', return_value=tray) as tray_factory, \
             patch('window_lifecycle.close_native') as close, \
             patch('app.threading.Event', return_value=quit_event):
            def explicit_quit():
                backend.shutdown.assert_not_called()
                tray_factory.call_args.kwargs['on_quit']()
            quit_event.wait.side_effect = explicit_quit
            app.run_app(Mock(), Mock())
        quit_event.wait.assert_called_once()
        quit_event.set.assert_called_once()
        close.assert_called_once_with(fake_window)
        tray.stop.assert_called_once()

    def test_close_before_webview_ready_hides_native_form_without_waiting(self):
        window = Mock()
        window.native.Handle.ToInt64.return_value = 1234
        window.events.shown.is_set.return_value = False
        with patch('window_lifecycle.user32') as native:
            self.assertIs(hide_to_background(window), False)
            native.ShowWindow.assert_called_once_with(1234, 0)
        window.hide.assert_not_called()

    def test_close_is_cancelled_even_when_native_hide_fails(self):
        window = Mock()
        with patch('window_lifecycle.user32.ShowWindow', side_effect=RuntimeError('Window not ready')):
            self.assertIs(hide_to_background(window), False)

    def test_indicator_recreates_its_window_after_render_failure(self):
        created=[]
        class FakeWindow:
            def __init__(self, *args):
                self.failed = not created
                self.closed = False
                created.append(self)
            def present(self, *args, **kwargs):
                if self.failed:
                    raise RuntimeError('Display connection lost')
            def close(self):
                self.closed = True
        with patch('overlay.LayeredWindow', FakeWindow):
            overlay = FloatingOverlay()
            try:
                self.assertTrue(overlay.ready_event.is_set())
                self.assertEqual(len(created), 2)
                self.assertTrue(created[0].closed)
                self.assertTrue(overlay.thread.is_alive())
            finally:
                overlay.close()
                overlay.thread.join(2)
            self.assertTrue(created[1].closed)

    def test_indicator_cannot_be_disabled_by_old_setting(self):
        backend = AppBackend.__new__(AppBackend)
        backend.config = {}
        backend._overlay = Mock()
        with patch('backend.save_config'):
            backend.set_setting('show_overlay', False)
        self.assertTrue(backend.config['show_overlay'])
        backend._overlay.close.assert_not_called()
        backend._overlay.ensure_visible.assert_called_once()

    def test_gpu_warmup_failure_falls_back_to_cpu(self):
        gpu, cpu = Mock(), Mock()
        gpu.transcribe.side_effect = RuntimeError('CUDA DLL unavailable')
        cpu.transcribe.return_value = ([], None)
        with patch('transcriber.WhisperModel', side_effect=[gpu, cpu]) as factory, \
             patch('transcriber.ctranslate2.get_supported_compute_types', side_effect=[{'float16'}, {'int8'}]):
            engine = WhisperTranscriber()
        self.assertEqual(engine.device, 'cpu')
        self.assertEqual(engine.compute_type, 'int8')
        self.assertIs(engine.model, cpu)
        self.assertEqual([call.kwargs['device'] for call in factory.call_args_list], ['cuda','cpu'])

    def test_failed_cpu_warmup_does_not_claim_ready(self):
        model = Mock()
        model.transcribe.side_effect = RuntimeError('Engine failure')
        with patch('transcriber.WhisperModel', return_value=model), \
             patch('transcriber.ctranslate2.get_supported_compute_types', return_value={'int8'}):
            with self.assertRaisesRegex(RuntimeError, 'Préparation du moteur impossible'):
                WhisperTranscriber(device='cpu', compute_type='int8')

    def test_recording_does_not_wait_for_hidden_webview(self):
        backend = AppBackend.__new__(AppBackend)
        backend._ui_queue = queue.Queue()
        backend._closing = False
        backend._window = Mock()
        entered, release = threading.Event(), threading.Event()
        def slow_webview(script):
            entered.set()
            release.wait(3)
        backend._window.evaluate_js.side_effect = slow_webview
        backend._lock = threading.Lock()
        backend._model_loading = False
        backend._transcriber = Mock()
        backend._recorder = Mock()
        backend._recorder.stop.return_value = np.zeros(16000)
        backend._overlay = Mock()
        backend.config = {}
        backend.is_recording = False
        worker = threading.Thread(target=backend._ui_worker, daemon=True)
        worker.start()
        try:
            backend._notify_ui('slow notification')
            self.assertTrue(entered.wait(1))
            completed = threading.Event()
            def record_and_stop():
                self.assertTrue(backend.start_recording())
                backend.stop_recording()
                completed.set()
            hook = threading.Thread(target=record_and_stop, daemon=True)
            hook.start()
            self.assertTrue(completed.wait(.5), 'Input hook waited for WebView')
            self.assertFalse(backend.is_recording)
            backend._overlay.show_recording.assert_called_once()
            backend._overlay.show_transcribing.assert_called_once()
        finally:
            release.set()
            backend._ui_queue.put(None)
            worker.join(2)

    def test_native_alt_comma_registration_and_dispatch(self):
        import ctypes
        from ctypes import wintypes
        callback = Mock()
        calls = []
        def get_message(ptr, *args):
            if not calls:
                ctypes.cast(ptr, ctypes.POINTER(wintypes.MSG)).contents.message = 0x0312
                calls.append(True)
                return 1
            return 0
        with patch('paste_hotkey.user32') as win:
            win.RegisterHotKey.return_value = True
            win.GetAsyncKeyState.return_value = 0
            win.GetMessageW.side_effect = get_message
            hotkey = PasteHotkey(callback)
            hotkey._thread.join(2)
            hotkey.close()
            win.RegisterHotKey.assert_called_once_with(None, 1, 0x4001, 0xBC)
            callback.assert_called_once()
            win.UnregisterHotKey.assert_called_once_with(None, 1)

    def test_last_transcript_can_be_pasted_repeatedly(self):
        backend = AppBackend.__new__(AppBackend)
        backend._last_transcript = 'Bonjour, texte conservé.'
        with patch('backend.TextInjector.paste', return_value=4) as paste:
            self.assertEqual(backend.paste_last_transcript()['status'], 'ok')
            self.assertEqual(backend.paste_last_transcript()['status'], 'ok')
            self.assertEqual(paste.call_count, 2)
            paste.assert_called_with('Bonjour, texte conservé.')

    def test_empty_last_transcript_does_not_send_input(self):
        backend = AppBackend.__new__(AppBackend)
        backend._last_transcript = ''
        backend._report_error = Mock()
        with patch('backend.TextInjector.paste') as paste:
            self.assertEqual(backend.paste_last_transcript()['status'], 'empty')
            paste.assert_not_called()

    def test_paste_sends_complete_ctrl_v_sequence(self):
        with patch('injector.copy_text', return_value=True), patch('injector.release_held_modifiers'), patch('injector.user32') as win:
            win.SendInput.return_value = 4
            self.assertEqual(TextInjector.paste('Bonjour'), 4)
            events = win.SendInput.call_args.args[1]
            self.assertEqual([event.ki.wVk for event in events], [0x11, 0x56, 0x56, 0x11])
            self.assertEqual([event.ki.dwFlags for event in events], [0, 0, KEYEVENTF_KEYUP, KEYEVENTF_KEYUP])

    def test_clipboard_closes_after_copy_failure(self):
        with patch('injector.win32clipboard') as clip, patch('injector.time.sleep'):
            clip.SetClipboardText.side_effect = RuntimeError('busy')
            self.assertFalse(copy_text('Bonjour'))
            self.assertEqual(clip.CloseClipboard.call_count, 5)

    def test_microphone_recovery_does_not_deadlock(self):
        stream = Mock(active=True)
        with patch('recorder.sd.InputStream', return_value=stream):
            rec = AudioRecorder()
            stream.active = False
            stream.start.side_effect = lambda: setattr(stream, 'active', True)
            worker = threading.Thread(target=rec.start, daemon=True)
            worker.start()
            worker.join(2)
            self.assertFalse(worker.is_alive(), 'Microphone recovery deadlocked')
            self.assertTrue(rec.is_recording)
            rec.close()

    def test_missing_microphone_reports_failure(self):
        with patch('recorder.sd.InputStream', side_effect=RuntimeError('disconnected')):
            rec = AudioRecorder()
            with self.assertRaisesRegex(RuntimeError, 'Microphone indisponible'):
                rec.start()
            self.assertFalse(rec.is_recording)

    def test_shutdown_allows_audio_callback_to_finish(self):
        stream = Mock(active=True)
        with patch('recorder.sd.InputStream', return_value=stream):
            rec = AudioRecorder()
            def stop_stream():
                acquired = rec._lock.acquire(timeout=1)
                self.assertTrue(acquired, 'Shutdown retained callback lock')
                if acquired:
                    rec._lock.release()
            stream.stop.side_effect = stop_stream
            rec.close()

    def test_auto_language_becomes_none(self):
        transcriber = WhisperTranscriber.__new__(WhisperTranscriber)
        transcriber.model = Mock()
        transcriber.model.transcribe.return_value = ([], None)
        self.assertEqual(transcriber.transcribe(np.zeros(1600, dtype=np.float32), language='auto'), '')
        self.assertIsNone(transcriber.model.transcribe.call_args.kwargs['language'])

    def test_second_process_signals_existing_instance(self):
        name = 'Local\\WhisperFlow.Regression.' + str(os.getpid())
        first = SingleInstance(name)
        signalled = threading.Event()
        try:
            self.assertTrue(first.is_primary)
            first.watch(signalled.set)
            code = 'from single_instance import SingleInstance; s=SingleInstance(' + repr(name) + '); assert not s.is_primary; s.close()'
            subprocess.run([sys.executable, '-c', code], cwd=os.path.dirname(__file__), check=True, timeout=10)
            self.assertTrue(signalled.wait(2))
        finally:
            first.close()
        replacement = SingleInstance(name)
        try:
            self.assertTrue(replacement.is_primary)
        finally:
            replacement.close()

    def test_tray_does_not_join_itself(self):
        tray = TrayIcon()
        tray._thread = threading.current_thread()
        tray.stop()

    def test_transcription_exception_is_reported_and_overlay_reset(self):
        backend = AppBackend.__new__(AppBackend)
        backend._target_hwnd = None
        backend._closing = False
        backend._processing_lock = threading.Lock()
        backend._overlay = Mock()
        backend._process_audio = Mock(side_effect=RuntimeError('CUDA failure'))
        backend._report_error = Mock()
        backend._process_and_inject(np.zeros(16000))
        backend._report_error.assert_called_once()
        backend._overlay.hide.assert_called_once()
        self.assertFalse(backend._processing_lock.locked())


if __name__ == '__main__':
    unittest.main()
