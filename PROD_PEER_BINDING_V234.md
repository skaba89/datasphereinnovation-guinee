# V234-F13 — Liaison du processus Docker

Contrôle côté hôte du PID et UID SO_PEERCRED, identité exacte du conteneur et image, PID init Docker, génération StartedAt et starttime proc, pidfd et double observation. Le processus client doit être le PID init du conteneur; pas de wrapper ou docker exec. Linux avec pidfd requis.

Tests : `python -m unittest test_prod_private_peer_binding`. Socket et credentials réels, daemon Docker simulé. Ce contrôle ponctuel ne garantit pas la durée de vie après retour; intégrer la conservation du pidfd et la vérification avant émission dans le superviseur final. Le socket dédié et le contrôle des descripteurs transmis restent requis. Aucun lancement, aucune mutation Docker. Rollback : revert uniquement.
