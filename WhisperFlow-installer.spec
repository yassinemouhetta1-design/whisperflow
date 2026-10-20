# -*- mode: python ; coding: utf-8 -*-
# Spec PyInstaller pour WhisperFlow (build onedir complet : app + interface + moteur CUDA).
# Les DLL NVIDIA (cuBLAS/cuDNN) et le modèle sont ajoutés après coup par build_installer.bat.

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# Chemin du site-packages du .venv (pour les ressources hors-package)
SITE_PACKAGES = os.path.join(SPECPATH, '.venv', 'Lib', 'site-packages')
if not os.path.isdir(SITE_PACKAGES):
    # Repli : site-packages de l'interpréteur qui exécute PyInstaller
    SITE_PACKAGES = os.path.dirname(os.path.dirname(os.__file__))

# Données embarquées : interface web + icône + ressources du moteur
datas = [
    ('frontend', 'frontend'),
    ('assets', 'assets'),
]
# VAD Silero (onnx) embarquée dans faster_whisper
datas += collect_data_files('faster_whisper', include_py_files=False)
# Pilotes PortAudio de sounddevice (dossier, pas un package)
datas += [(os.path.join(SITE_PACKAGES, '_sounddevice_data'), '_sounddevice_data')]
# Librairies WebView2 / WinForms de pywebview (DLL interop)
datas += collect_data_files('webview', include_py_files=False)

binaries = []
binaries += collect_dynamic_libs('ctranslate2')
binaries += collect_dynamic_libs('onnxruntime')

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        # pywebview (backend Windows : WebView2 via WinForms/.NET)
        'webview.platforms.edgechromium',
        'webview.platforms.winforms',
        'clr',
        # pynput (backends Win32 des écouteurs globaux)
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        # Moteur de transcription
        'faster_whisper',
        'ctranslate2',
        'onnxruntime',
        'av',
        'tokenizers',
        'sounddevice',
        # Téléchargement de repli du modèle (si non embarqué)
        'huggingface_hub',
        'hf_xet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Inutiles dans l'exe final — allège le build
        'customtkinter',  # ancienne interface, remplacée par pywebview
        'PyInstaller',
        'setuptools',
        'pip',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WhisperFlow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # ne jamais compresser les DLL CUDA
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='WhisperFlow',
)
