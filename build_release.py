"""Build the complete Windows installer without deleting local project files."""
from pathlib import Path
import importlib.metadata as metadata
import os
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent


def download_microsoft(name, url):
    destination = ROOT / 'prerequisites' / name
    destination.parent.mkdir(exist_ok=True)
    if not destination.is_file():
        urllib.request.urlretrieve(url, destination)
    literal = str(destination).replace("'", "''")
    script = (f"$s = Get-AuthenticodeSignature -LiteralPath '{literal}'; "
              "if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Microsoft Corporation') { exit 1 }")
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], check=True)


def copy_licenses(bundle):
    target = bundle / 'licenses'
    target.mkdir(exist_ok=True)
    for distribution in metadata.distributions():
        name = distribution.metadata.get('Name', 'unknown')
        for entry in distribution.files or []:
            if '.dist-info' not in str(entry) or not any(word in entry.name.lower() for word in ('license', 'copying', 'notice')):
                continue
            source = Path(distribution.locate_file(entry))
            if source.is_file():
                folder = target / name
                folder.mkdir(exist_ok=True)
                shutil.copy2(source, folder / entry.name)
    urllib.request.urlretrieve('https://raw.githubusercontent.com/openai/whisper/main/LICENSE', target / 'OpenAI-Whisper-MIT.txt')


def main():
    if sys.platform != 'win32':
        raise SystemExit('Build Windows uniquement.')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', 'WhisperFlow-installer.spec'], cwd=ROOT, check=True)
    subprocess.run([sys.executable, 'assemble_bundle.py'], cwd=ROOT, check=True)
    bundle = ROOT / 'dist' / 'WhisperFlow'
    copy_licenses(bundle)
    shutil.copy2(ROOT / 'README.md', bundle / 'LIRE-MOI.md')
    download_microsoft('vc_redist.x64.exe', 'https://aka.ms/vc14/vc_redist.x64.exe')
    download_microsoft('WebView2RuntimeInstallerX64.exe', 'https://go.microsoft.com/fwlink/?linkid=2124701')
    candidates = [Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Inno Setup 6/ISCC.exe',
                  Path(os.environ.get('ProgramFiles(x86)', '')) / 'Inno Setup 6/ISCC.exe',
                  Path(os.environ.get('ProgramFiles', '')) / 'Inno Setup 6/ISCC.exe']
    compiler = next((path for path in candidates if path.is_file()), None)
    if compiler is None:
        raise SystemExit('Installez Inno Setup 6. Le bundle portable est prêt dans dist/WhisperFlow.')
    subprocess.run([str(compiler), 'installer.iss'], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
