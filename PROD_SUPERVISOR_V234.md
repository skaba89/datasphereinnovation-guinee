# V234-F8 — Superviseur : collecte consolidée

Le superviseur consolide les mesures hôte, image, conteneur et volume, puis répète la collecte complète. Le domaine de revue est distinct du contrat runtime V2 : la clé review_observation_sha256 ne doit jamais être renommée pour signer un conteneur exécutable. Aucun nonce consommé ni opération Docker mutante.

Tests : `python -m unittest test_prod_private_supervisor`. Les observations sont simulées. Le lancement effectif exige encore une topologie exécutable distincte, un contrôle complet de cette topologie, un canal d'autorisation non falsifiable vers le processus et la réservation V2 au dernier moment. La qualification sur le VPS reste obligatoire. Rollback : revert du code uniquement.
