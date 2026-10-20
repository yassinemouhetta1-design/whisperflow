"""
WhisperFlow - Assemblage du bundle après compilation PyInstaller.

Copie dans dist/WhisperFlow :
- les DLL NVIDIA (cuBLAS, cuDNN, nvrtc) à plat dans _internal ;
- le modèle large-v3-turbo depuis le cache HuggingFace (déréférencé),
  pour un fonctionnement 100 % hors-ligne après installation.
"""

import glob
import os
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE, "dist", "WhisperFlow")
INT_DIR = os.path.join(APP_DIR, "_internal")
SITE = os.path.join(BASE, ".venv", "Lib", "site-packages")

HF_HUB = os.path.join(
    os.environ.get("USERPROFILE", os.path.expanduser("~")),
    ".cache", "huggingface", "hub",
)


def copy_nvidia_dlls():
    """Copie les DLL CUDA à plat dans _internal (résolution standard PyInstaller)."""
    packages = ("cublas", "cudnn", "cuda_nvrtc")
    total = 0
    for pkg in packages:
        pattern = os.path.join(SITE, "nvidia", pkg, "bin", "*.dll")
        dlls = glob.glob(pattern)
        if not dlls:
            print(f"[!] Paquet NVIDIA {pkg} introuvable dans le .venv")
            continue
        for dll in dlls:
            shutil.copy2(dll, INT_DIR)
            total += 1
    print(f"[+] {total} DLL NVIDIA copiees dans _internal")


def copy_model():
    """Copie le snapshot du modele embarque (dereference les liens symboliques)."""
    repo = os.path.join(HF_HUB, "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo")
    snapshots = sorted(glob.glob(os.path.join(repo, "snapshots", "*")))
    src = next((s for s in snapshots if os.path.isfile(os.path.join(s, "model.bin"))), None)

    if src is None:
        from huggingface_hub import snapshot_download
        print('[*] Telechargement du modele pour l\'installation hors ligne...')
        src = snapshot_download('mobiuslabsgmbh/faster-whisper-large-v3-turbo',
            allow_patterns=['model.bin', 'config.json', 'tokenizer.json',
                            'preprocessor_config.json', 'vocabulary.json'])
        if not os.path.isfile(os.path.join(src, 'model.bin')):
            raise RuntimeError('Modele incomplet : model.bin absent')

    dst = os.path.join(APP_DIR, "models", "large-v3-turbo")
    if os.path.isfile(os.path.join(dst, "model.bin")):
        print("[+] Modele deja present, copie ignoree")
        return True

    # symlinks=False : copie le contenu reel des blobs vises par le snapshot
    shutil.copytree(src, dst, symlinks=False)
    size_gb = sum(
        os.path.getsize(os.path.join(r, f))
        for r, _, files in os.walk(dst)
        for f in files
    ) / (1024 ** 3)
    print(f"[+] Modele copie ({size_gb:.2f} Go) dans models/large-v3-turbo")
    return True


def main():
    if not os.path.isdir(INT_DIR):
        print("[!] dist/WhisperFlow/_internal introuvable : lancez d'abord PyInstaller.")
        return 1
    copy_nvidia_dlls()
    return 0 if copy_model() else 1


if __name__ == "__main__":
    sys.exit(main())
