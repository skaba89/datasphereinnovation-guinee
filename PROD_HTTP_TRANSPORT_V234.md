# V234-F9 — Qualification du transport HTTP

Le test ouvre un véritable socket HTTP loopback éphémère en DEV, avec le serveur borné existant. Seules deux routes synthétiques de qualification sont exposées; elles ne représentent pas la readiness métier. Le mode PROD et REC sont refusés. Aucun accès au volume, aux comptes ou aux documents.

Le point d'entrée métier et compose.prod.yaml restent verrouillés. Le contrat V2 n'est pas encore relié à un canal de lancement de confiance. Avant de créer une topologie exécutable, définir le canal de remise du permis, la preuve de consommation durable, l'enrôlement hors exposition métier, le verrou de durée de vie et les contrôles de redémarrage. Aucun simple flag d'environnement ne doit lever le verrou.

Tests : `python -m unittest test_prod_private_http_transport test_prod_lock`. Rollback : revert de la PR, aucun service ou volume à modifier.
