# V234-F1 — Qualification du scanner privé

Le module `prod_private_scanner.inspect()` exige le mode PROD et le chemin de socket prévu. Il utilise le client INSTREAM existant pour contrôler un contenu sain et le fichier de test EICAR inoffensif, puis vérifie la stabilité de l'identité du socket. Aucun contenu client ni réponse brute du scanner n'est journalisé par ce module.

Tests : `python -m unittest test_prod_private_scanner` (socket Unix réel, réponses simulées). La qualification du véritable daemon ClamAV depuis le conteneur final, le contrôle de la fraîcheur des signatures et l'intégration au point d'entrée restent nécessaires. Le test EICAR peut déclencher une alerte antivirus attendue. Aucun démarrage ou changement des verrous PROD.

Rollback : revert de cette PR uniquement; ne modifier ni le scanner partagé ni les autres services.
