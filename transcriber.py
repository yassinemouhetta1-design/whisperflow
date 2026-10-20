"""
WhisperFlow - Transcriber
Module de transcription haute performance basé sur faster-whisper (CTranslate2).
Optimisé pour GPU NVIDIA RTX 4050 (Ada Lovelace, FP16 Tensor Cores, Large-v3-Turbo).
"""

import os
import sys
import time
import logging
import gc
import numpy as np

_dll_handles = []

def app_base_dir():
    """Dossier d'installation : dossier de l'exécutable gelé, ou du script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def setup_cuda_env():
    """
    Enregistre les bibliothèques dynamiques NVIDIA (cuBLAS, cuDNN)
    pour garantir l'accélération matérielle CUDA sans erreur DLL.
    """
    search_dirs = []

    if getattr(sys, "frozen", False):
        # Build PyInstaller onedir : toutes les DLL (ctranslate2, cuBLAS, cuDNN)
        # sont copiées à plat dans _internal à côté de l'exécutable.
        exe_dir = os.path.dirname(sys.executable)
        search_dirs.append(os.path.join(exe_dir, "_internal"))
        search_dirs.append(os.path.join(exe_dir, "nvidia"))
    else:
        # Exécution depuis les sources : DLL dans le .venv du projet.
        base_dir = os.path.dirname(os.path.abspath(__file__))
        search_dirs.append(os.path.join(base_dir, ".venv", "Lib", "site-packages", "nvidia"))

    for base in search_dirs:
        if os.path.exists(base):
            if any(name.lower().endswith('.dll') for name in os.listdir(base)):
                _dll_handles.append(os.add_dll_directory(base))
            for root, dirs, files in os.walk(base):
                if "bin" in dirs:
                    p = os.path.join(root, "bin")
                    try:
                        _dll_handles.append(os.add_dll_directory(p))
                    except Exception:
                        pass
                    os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")

setup_cuda_env()

from faster_whisper import WhisperModel
import ctranslate2

def resolve_model_path(model_size):
    """
    Résout le chemin du modèle :
    1. Modèle embarqué dans l'installation (dossier models/<taille> à côté
       de l'exécutable) — 100 % hors-ligne, aucun téléchargement.
    2. Repli : nom court (cache HuggingFace local, sinon téléchargement).
    """
    bundled = os.path.join(app_base_dir(), "models", model_size)
    if os.path.isfile(os.path.join(bundled, "model.bin")):
        return bundled
    return model_size

class WhisperTranscriber:
    def __init__(self, model_size="large-v3-turbo", device="cuda", compute_type="float16"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

        model_path = resolve_model_path(model_size)
        print(f"[*] Chargement du modèle {model_size} sur {device} ({compute_type})...")
        t0 = time.perf_counter()

        self.model = None
        candidates = [(device, compute_type)]
        if device in ('cuda', 'auto'):
            candidates.append(('cpu', 'int8'))
        for index, (candidate_device, candidate_compute) in enumerate(candidates):
            try:
                if candidate_device != 'auto':
                    supported = ctranslate2.get_supported_compute_types(candidate_device)
                    if candidate_compute not in supported:
                        candidate_compute = next(kind for kind in
                            ('float16', 'int8_float32', 'int8', 'float32') if kind in supported)
                self.device, self.compute_type = candidate_device, candidate_compute
                self.model = WhisperModel(model_size_or_path=model_path,
                    device=candidate_device, compute_type=candidate_compute,
                    num_workers=1, cpu_threads=4)
                self.warmup()
                break
            except (RuntimeError, ValueError, OSError) as error:
                self.model = None
                gc.collect()
                if index == len(candidates) - 1:
                    raise
                logging.warning('Accélération GPU indisponible, repli CPU : %s', error)
        t_load = (time.perf_counter() - t0) * 1000
        print(f"[+] Modèle chargé en {t_load:.1f}ms")


    def warmup(self):
        """
        Pré-chauffe les cœurs Tensor CUDA, le compilateur JIT cuBLAS et le VAD Silero
        avec 0.1s d'audio de silence. Élimine tout pic de latence initial.
        """
        print("[*] Pré-chauffage du moteur CUDA & VAD (warm-up)...")
        t0 = time.perf_counter()
        silence = np.zeros(1600, dtype=np.float32)  # 0.1s à 16kHz

        try:
            # 1. Warm-up de l'encodeur / décodeur Transformer Whisper (forces cuBLAS kernel init)
            list(self.model.transcribe(
                silence,
                language="fr",
                beam_size=1,
                vad_filter=False,
                condition_on_previous_text=False
            )[0])

            # 2. Warm-up du filtre VAD (Silero)
            list(self.model.transcribe(
                silence,
                language="fr",
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False
            )[0])

            dt = (time.perf_counter() - t0) * 1000
            print(f"[+] Moteur prêt en {dt:.1f}ms ({self.device}, {self.compute_type})")
        except Exception as e:
            raise RuntimeError(f"Préparation du moteur impossible : {e}") from e

    def transcribe(self, audio_array, language="fr", beam_size=1, vad_filter=True):
        """
        Transcrit un tableau numpy float32 (16kHz mono).
        Optimisé pour une latence ultra-faible (< 250ms sur RTX 4050).
        """
        if audio_array is None or len(audio_array) == 0:
            return ""

        # Assurer un tableau float32 contigu
        if not isinstance(audio_array, np.ndarray) or audio_array.dtype != np.float32 or not audio_array.flags.c_contiguous:
            audio_array = np.ascontiguousarray(audio_array, dtype=np.float32)

        # Paramètres VAD pour détection rapide et sans queue de silence superflue
        vad_params = dict(
            min_silence_duration_ms=300,
            threshold=0.5
        ) if vad_filter else None

        segments, info = self.model.transcribe(
            audio_array,
            language=None if language == "auto" else language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            vad_parameters=vad_params,
            condition_on_previous_text=False,
            temperature=0.0,
            without_timestamps=True
        )

        text_parts = [segment.text.strip() for segment in segments]
        full_text = " ".join(text_parts).strip()
        return full_text
