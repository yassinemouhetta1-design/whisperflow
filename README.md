# WhisperFlow

Application Windows de dictée vocale locale, avec le modèle Whisper large-v3-turbo embarqué dans l'installateur. Interface française, accélération NVIDIA et repli sur le processeur lorsque le GPU ne peut pas être utilisé.

Pour installer l'application sur un autre PC, ouvre la [dernière version](https://github.com/yassinemouhetta1-design/whisperflow/releases/latest). Télécharge les deux fichiers part1/part2 et Installer-WhisperFlow.cmd dans le même dossier, puis lance le fichier CMD. Il reconstitue l'installateur, vérifie son empreinte SHA-256 et le lance. GitHub limite chaque pièce jointe à 2 Gio ; l'installateur complet fait environ 3,21 Go.

Windows 10 version 1809 ou plus récent, ou Windows 11, en x64, est requis. Prévoir environ 10 Go libres. Les composants Microsoft Visual C++ et WebView2 sont inclus dans l'installateur hors ligne. Pour l'accélération GPU, le pilote NVIDIA doit être à jour. Le repli CPU fonctionne mais peut être nettement plus lent.

Place le curseur dans un champ de texte, maintiens Ctrl + Win pendant que tu parles, puis relâche. Mouse5 démarre et arrête aussi la dictée ; Échap annule. Les raccourcis se personnalisent dans l'application. Si tu changes de fenêtre pendant la transcription, le texte est copié plutôt qu'inséré dans une autre application.

La jauge est fixe en bas au centre. Elle démarre avant le moteur vocal, reste à 50 % au repos et passe à 100 % pendant la dictée. Elle laisse passer les clics et se recrée en cas de panne d'affichage. La croix, Alt+F4 et Fermer la fenêtre masquent l'interface. Pour arrêter l'app, utilise Quitter WhisperFlow dans l'icône de notification ou le Gestionnaire des tâches.

La transcription est locale. Le dépôt et les pièces jointes ne contiennent pas d'historique de dictée, de configuration personnelle ou de profil de navigateur. Les réglages et journaux du destinataire sont créés dans son propre dossier AppData. Le programme n'est pas un produit officiel Wispr Flow ni une application OpenAI officielle.

## Développement

Utilise Python 3.11 x64 sous Windows. Le premier chargement depuis les sources télécharge le modèle si son cache est vide.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-gpu.txt
.\.venv\Scripts\python.exe app.py
```

Pour une exécution sur CPU sans les bibliothèques CUDA redistribuables, utilise requirements.txt. Le moteur bascule sur CPU si CUDA n'est pas disponible.

```powershell
.\.venv\Scripts\python.exe -m unittest test_regressions
```

Pour construire l'installateur complet, installe Inno Setup 6 puis lance build_installer.bat. Le script compile app.py, ajoute les bibliothèques NVIDIA et le modèle, copie les licences et télécharge les installateurs Microsoft depuis leurs liens officiels en vérifiant leurs signatures. Le téléchargement du modèle représente environ 1,6 Go. Le résultat est créé dans Installer/. Aucun dossier utilisateur n'est supprimé par le script.

La configuration portable peut être copiée depuis config.example.json vers config.json ; elle est ignorée par Git. Dans une installation normale, les réglages résident dans %APPDATA%\WhisperFlow.

## Validation

La [revue de la version 1.1.1](docs/REVIEW-1.1.1.md) décrit les corrections et les limites des vérifications. Les 20 tests de régression passent. Le paquet compilé a transcrit une phrase française sur GPU et CPU avec un profil isolé et le téléchargement de modèles désactivé. La fermeture dès le lancement, le maintien en arrière-plan et le rendu réel de la jauge ont été vérifiés sur le PC de préparation. Aucun test sur le PC destinataire ou une machine Windows vierge n'a été effectué.

Les composants tiers conservent leurs licences respectives, fournies dans licenses/ dans l'application installée. L'installateur de l'application n'est pas signé avec un certificat éditeur ; les installateurs Microsoft embarqués ont une signature Microsoft valide.
