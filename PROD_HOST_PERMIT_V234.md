# V234-B — Réservation du permis privé

Le composant `prod_private_host_permit.reserve` appelle la mesure V234-A sans injection de runner, vérifie la signature V233 avec les digests mesurés, puis réserve le nonce via le registre V233. Un échec avant réservation ne consomme rien. Une réservation réussie ne peut pas être réutilisée pour démarrer un processus et ne délivre aucune capacité runtime.

L'appelant doit être un opérateur de confiance, avec clé publique et empreinte provisionnées indépendamment, preuves approuvées et registre préexistant. Ce composant ne provisionne pas cette confiance, ne mesure pas le conteneur réel et ne résout pas les courses entre mesure et démarrage. Ne pas l'exécuter avec un vrai permis tant que la chaîne de lancement n'est pas intégrée.

Tests : `python -m unittest test_prod_private_host_permit test_prod_private_replay test_prod_private_release`. Rollback : revert du code uniquement, ne jamais réinitialiser le registre anti-rejeu. Les verrous serveur et Compose restent inchangés.
