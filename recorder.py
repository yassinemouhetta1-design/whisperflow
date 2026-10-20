"""
WhisperFlow - Audio Recorder
Module de capture audio optimisé 16kHz mono via sounddevice.
Flux persistant en arrière-plan avec pré-buffer circulaire (zero-lag & anti-clipping).
"""

import threading
import logging
import sounddevice as sd
import numpy as np
from collections import deque

class AudioRecorder:
    def __init__(self, sample_rate=16000, pre_buffer_ms=200, blocksize=512):
        self.sample_rate = sample_rate
        self.channels = 1
        self.dtype = np.float32
        self.blocksize = blocksize  # ~32ms par bloc à 16kHz

        # Pré-buffer circulaire pour capturer les 200ms précédant la frappe (zéro mot coupé)
        max_blocks = max(2, int((sample_rate * (pre_buffer_ms / 1000.0)) / self.blocksize))
        self._pre_buffer = deque(maxlen=max_blocks)

        self.is_recording = False
        self._frames = []
        self._lock = threading.Lock()
        self._stream_lock = threading.Lock()

        self.stream = None
        self._init_stream()

    def _init_stream(self):
        """Initialise ou réinitialise le flux audio sounddevice persistant."""
        with self._stream_lock:
            if self.stream is not None:
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None

            try:
                self.stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype='float32',
                    blocksize=self.blocksize,
                    callback=self._audio_callback
                )
                self.stream.start()
            except Exception as e:
                if self.stream is not None:
                    try:
                        self.stream.close()
                    except Exception:
                        pass
                self.stream = None
                logging.exception("Initialisation du microphone impossible")

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback audio haute performance exécuté dans le thread temps réel WASAPI."""
        # indata a la forme (blocksize, 1)
        chunk = indata.copy().flatten()
        with self._lock:
            if self.is_recording:
                self._frames.append(chunk)
            else:
                self._pre_buffer.append(chunk)

    def start(self):
        """
        Déclenchement instantané (< 0.05 ms).
        Active la capture et intègre immédiatement le pré-buffer circulaire
        pour garantir qu'aucune première syllabe n'est tronquée.
        """
        # Never hold the callback's buffer lock while opening/stopping a stream.
        if self.stream is None or not self.stream.active:
            self._init_stream()
        if self.stream is None or not self.stream.active:
            raise RuntimeError("Microphone indisponible. Vérifiez le périphérique audio.")
        with self._lock:
            # Injection immédiate du pré-buffer
            self._frames = list(self._pre_buffer)
            self._pre_buffer.clear()
            self.is_recording = True

    def stop(self):
        """
        Arrête l'enregistrement et retourne l'audio float32 mono à 16kHz sous forme de ndarray.
        Opération instantanée sans fermeture du flux matériel.
        """
        with self._lock:
            self.is_recording = False
            if not self._frames:
                return np.array([], dtype=np.float32)

            audio = np.concatenate(self._frames, axis=0).astype(np.float32)
            self._frames = []
            return audio

    def cancel(self):
        """Annule l'enregistrement en cours et vide les buffers."""
        with self._lock:
            self.is_recording = False
            self._frames = []
            self._pre_buffer.clear()

    def close(self):
        """Ferme proprement le périphérique audio lors de l'arrêt de l'application."""
        with self._lock:
            self.is_recording = False
            self._frames = []
            self._pre_buffer.clear()
        with self._stream_lock:
            if self.stream is not None:
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
