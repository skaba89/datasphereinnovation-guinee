# V234-F2 — Préflight combiné du runtime

Le module vérifie l'identité réelle du processus, sa configuration PROD, l'absence de token administrateur générique, la base existante sous verrou consultatif, la readiness nominative, le déchiffrement effectif des secrets MFA et le scanner. Il ne crée aucune donnée et ne démarre aucun serveur.

Les références REC et candidate doivent provenir d'une collecte indépendante. Le volume doit être exclusivement contrôlé et aucun écrivain actif. Les contrôles MFA exigent un enrôlement préalable : ce préflight concerne donc le service métier après la phase d'activation, et non le premier accès d'enrôlement. Une cérémonie d'activation isolée reste nécessaire. Le verrou est libéré au retour; il ne constitue pas une autorisation de lancement.

Tests : `python -m unittest test_prod_private_runtime_preflight`. Les dépendances sont simulées; qualification réelle Docker et ClamAV requise. Le contrôle de signature, la réservation du nonce et la liaison au conteneur final doivent être intégrés dans un superviseur de lancement avant toute suppression des verrous. Rollback : revert de cette PR sans toucher aux volumes, au proxy ou aux services.
