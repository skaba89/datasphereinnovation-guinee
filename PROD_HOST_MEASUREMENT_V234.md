# V234-A — Mesures hôte

Le module mesure une image locale référencée par digest via le socket Docker local et vérifie son ID de configuration, son utilisateur et son label OCI revision. Les identités attendues doivent provenir d'une release approuvée indépendamment. Une image sans label est refusée. Le label seul ne prouve pas la provenance.

Les octets JSON fournis sont validés et hachés sans affichage des secrets. Ils doivent provenir d'une résolution Compose contrôlée par l'opérateur; ce module ne collecte pas lui-même cette configuration et ne mesure pas un conteneur réel. La complétude des preuves ne prouve pas leur authenticité. Une double lecture Docker réduit les changements observables sans éliminer les courses entre contrôle et utilisation.

Tests ciblés : `python -m unittest test_prod_private_host_measurement`.

Aucune commande de démarrage, aucun nonce consommé, aucune autorisation runtime. Les verrous server.py et Compose restent actifs. Rollback : abandonner ou revert cette PR, sans toucher aux volumes ni aux autres services. Les tests réels du daemon, l'intégration de la confiance, la liaison à la configuration runtime, le bootstrap nominatif, ClamAV et la restauration restent obligatoires avant GO.
