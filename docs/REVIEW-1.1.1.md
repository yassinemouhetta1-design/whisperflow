WhisperFlow 1.1.1 — revue et validation du 20 octobre 2026

Le fichier à envoyer est WhisperFlow-Setup-1.1.1-Windows-x64.exe. Il contient l'application, son interface, le modèle large-v3-turbo, les bibliothèques NVIDIA nécessaires et les installateurs hors ligne Microsoft Visual C++ et WebView2. Python et le toolkit CUDA ne sont pas nécessaires sur le PC destinataire. Le pilote NVIDIA doit être installé et à jour pour l'accélération GPU.

La cible est Windows 10 version 1809 ou plus récent, ou Windows 11, en 64 bits. Prévoir environ 10 Go d'espace libre pendant l'installation. La configuration et les journaux du destinataire sont créés dans son propre dossier AppData. Aucun historique de dictée, profil de navigateur ni réglage personnel du PC de préparation n'est inclus dans le paquet.

La revue a corrigé la détection WebView2 : l'ancien installateur utilisait un identifiant de registre incorrect. Le nouvel installateur vérifie le Runtime puis utilise l'installateur Microsoft embarqué lorsqu'il manque. Les installateurs WebView2 et Visual C++ téléchargés ont tous deux une signature Authenticode Microsoft valide. Cette méthode de distribution hors ligne est documentée par [Microsoft](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution). La source du redistribuable Visual C++ est la [page officielle Microsoft](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).

La recherche des bibliothèques CUDA a été corrigée pour charger aussi les DLL placées directement dans le dossier interne de l'application. Une erreur de préchauffage du moteur ne passe plus silencieusement pour un chargement réussi. Le moteur choisit un type de calcul compatible et essaie le processeur si le GPU ne peut pas fonctionner. Le repli CPU est plus lent ; les performances dépendent du PC. Les exigences matérielles du moteur sont décrites dans la [documentation CTranslate2](https://opennmt.net/CTranslate2/hardware_support.html).

La jauge est créée avant l'initialisation du micro, de WebView2 et du moteur de transcription. Elle est permanente, fixe en bas au centre, à 50 % au repos et 100 % pendant la dictée, avec des clics traversants. Une panne de dessin déclenche la recréation de sa fenêtre. Une ancienne configuration ne peut plus désactiver la jauge.

La fermeture de la fenêtre, y compris pendant le chargement initial, est annulée et remplacée par un masquage natif sans attendre WebView2. Si l'interface s'arrête de façon inattendue, le processus conserve la dictée, la jauge et l'icône de notification jusqu'à une demande explicite de quitter. Les mises à jour de l'interface sont envoyées sur un fil séparé afin de ne pas bloquer les raccourcis globaux.

Les 20 tests de régression passent. Ils couvrent notamment le repli CPU après une panne CUDA, les erreurs de préchauffage, la recréation de la jauge, l'impossibilité de la masquer via un ancien réglage, la fermeture avant le chargement de WebView2 et le maintien du moteur après un arrêt de l'interface.

Sur l'exécutable compilé installé, un test a fermé la fenêtre principale immédiatement après son apparition. La jauge a continué de se dessiner. Ctrl + Win a démarré la dictée en arrière-plan, la jauge a été vérifiée dans une capture réelle à 100 %, puis elle est revenue à 50 % après annulation. Le test utilisait un champ local isolé et n'a envoyé aucun texte dans une autre application. Le masquage forcé de la jauge et sa tentative de fermeture ont également été testés : elle est réapparue et la fermeture a été ignorée.

Le paquet compilé a été testé avec un profil AppData isolé, un cache de modèles vide, le mode hors ligne activé et un PATH limité à Windows. Le modèle embarqué a transcrit « Bonjour, ceci est un test. » sur GPU CUDA en float16, puis sur CPU en int8. Les durées complètes, chargement et préchauffage inclus, étaient respectivement de 8,115 s et 19,302 s sur ce PC ; ce ne sont pas des mesures de latence de dictée après chargement.

Les licences des composants redistribués, dont celles de NVIDIA et la licence MIT de Whisper, sont incluses dans le dossier licenses de l'application installée. L'installateur WhisperFlow lui-même n'est pas signé avec un certificat éditeur.

Limite de validation : ces vérifications ont été effectuées sur le PC de préparation, avec des profils et caches isolés. L'installation n'a pas été exécutée sur le PC destinataire ni dans une machine Windows vierge. Sa compatibilité finale dépend notamment du pilote, du micro et des politiques Windows de ce PC.

Le fichier final contient 3212002287 octets. Son empreinte SHA-256 est : ce7fe4fc2cfdb121e7d5f8b3ececdb62ae4a8ff116f76395575bd32f1db3a5a7.
