# V234-C — Inspection du conteneur de revue

Le module `prod_private_container_binding.inspect` compare un conteneur CREATED au modèle Compose verrouillé, avec identités attendues provisionnées indépendamment. Il contrôle notamment image, variables DSIG, utilisateur, port loopback, ressources, privilèges et destinations des montages. Deux observations doivent être identiques. Aucun secret ni résultat brut Docker n'est retourné.

Ce contrôle partiel ne constitue pas une attestation complète de runtime : le réseau réel, les options de volume, les variables non DSIG, les autres paramètres Docker et les courses après inspection restent à traiter. La commande de démarrage reste volontairement bloquée. Les tests utilisent des observations simulées ; le daemon réel doit être qualifié avant toute utilisation.

Tests : `python -m unittest test_prod_private_container_binding`. Rollback : revert de cette PR, aucune modification des volumes, du proxy ou des services. Aucun permis consommé.
