"""Offline deployment check; never opens the microphone or injects keys."""
import argparse
import json
import os
import time
import wave
import numpy as np


def run_self_test(arguments):
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', required=True, metavar='REPORT_JSON')
    parser.add_argument('--audio')
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    args = parser.parse_args(arguments)
    result = {'ok': False, 'requested_device': args.device}
    started = time.perf_counter()
    try:
        from transcriber import WhisperTranscriber, resolve_model_path
        path = resolve_model_path('large-v3-turbo')
        if not os.path.isfile(os.path.join(path, 'model.bin')):
            raise RuntimeError('Le modèle embarqué est absent')
        audio = np.zeros(1600, dtype=np.float32)
        if args.audio:
            with wave.open(args.audio, 'rb') as stream:
                if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, 16000):
                    raise ValueError('Audio de test requis : WAV mono PCM 16 bits, 16000 Hz')
                audio = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').astype(np.float32) / 32768
        engine = WhisperTranscriber(device=args.device,
            compute_type='int8' if args.device == 'cpu' else 'float16')
        text = engine.transcribe(audio, language='fr')
        result.update(ok=True, bundled_model=True, actual_device=engine.device,
                      compute_type=engine.compute_type, text=text)
    except Exception as error:
        result['error'] = str(error)
    result['elapsed_seconds'] = round(time.perf_counter() - started, 3)
    with open(args.self_test, 'w', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    return 0 if result['ok'] else 1
