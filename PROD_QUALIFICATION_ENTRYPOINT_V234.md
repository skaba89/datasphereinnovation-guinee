# V234-F14 — Qualification intégrée du point d'entrée

Le destinataire ouvre un véritable serveur HTTP de qualification en DEV uniquement après un échange Unix socket signé et la réservation du nonce par l'émetteur. Un second échange avec le même permis ne doit pas ouvrir de listener. Les routes métier restent absentes. Les tests utilisent des clés synthétiques, des identités simulées et un registre temporaire.

Tests : `python -m unittest test_prod_private_qualification_entrypoint test_prod_lock`. Ce parcours ne qualifie pas Docker réel, ne lie pas encore le PID Docker au superviseur, ne conserve pas le verrou du volume métier et ne constitue pas le point d'entrée PROD. Il reste nécessaire d'intégrer ces contrôles et une topologie exécutable distincte avec confiance provisionnée. Aucun changement de Compose ou des services existants. Rollback : revert du code uniquement.
