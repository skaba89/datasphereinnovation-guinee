# V234-E2 — Qualification MFA persistante

Le test utilise le schéma métier réel, deux comptes synthétiques nominatifs et les handlers d'authentification existants avec une connexion SQLite distincte à chaque appel. Il vérifie activation, refus des droits avant MFA, confirmation TOTP, révocation de la session d'enrôlement, refus du mot de passe seul, code de secours à usage unique, logout et readiness des deux comptes.

Exécuter sous Linux non-root : `python -m unittest test_prod_private_persistent_mfa test_prod_named_mfa`. Aucun vrai compte, réseau ou serveur PROD. Les requêtes HTTP sont simulées au niveau du handler ; la qualification HTTPS réelle et la cérémonie d'activation des vrais administrateurs restent nécessaires. Aucun changement de runtime ni de verrous. Rollback : revert de la PR, aucun volume à modifier.
