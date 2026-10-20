@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop'; $root=(Get-Location).Path; $out=Join-Path $root 'WhisperFlow-Setup-1.1.1-Windows-x64.exe'; $parts=@('WhisperFlow-1.1.1-part1.bin','WhisperFlow-1.1.1-part2.bin'); foreach($p in $parts){if(-not (Test-Path -LiteralPath (Join-Path $root $p))){throw ('Fichier manquant : '+$p)}}; if(-not (Test-Path -LiteralPath $out)){Write-Host 'Assemblage de WhisperFlow...'; $dest=[IO.File]::Open($out,[IO.FileMode]::CreateNew); try{foreach($p in $parts){$src=[IO.File]::OpenRead((Join-Path $root $p)); try{$src.CopyTo($dest)}finally{$src.Dispose()}}}finally{$dest.Dispose()}}; if((Get-FileHash -LiteralPath $out -Algorithm SHA256).Hash.ToLower() -ne 'ce7fe4fc2cfdb121e7d5f8b3ececdb62ae4a8ff116f76395575bd32f1db3a5a7'){throw 'Empreinte incorrecte. Le fichier reconstitue est incomplet ou altere.'}; Write-Host 'Verification OK.'; if($env:WHISPERFLOW_ASSEMBLE_ONLY -ne '1'){Start-Process -FilePath $out}"
if errorlevel 1 (
  echo Echec. Gardez les deux parties et ce fichier dans le meme dossier.
  pause
  exit /b 1
)
