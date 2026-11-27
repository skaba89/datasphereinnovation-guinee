# V234-F3 — Revue de lancement côté hôte

Le module combine mesure locale, vérification du permis signé, inspection du conteneur arrêté et nouvelle vérification de la signature. Il ne consomme pas le nonce: le conteneur inspecté reste verrouillé et inutilisable pour servir HTTP. Aucun résultat de revue ne constitue une capacité de démarrage.

Tests : `python -m unittest test_prod_private_launch_review`. Les observations sont simulées dans ces tests. Le permis V233 ne signe pas directement l'identité du conteneur; celle-ci doit être liée dans un nouveau contrat de lancement, avec configuration runtime, autorité provisionnée hors conteneur, registre durable et contrôle exclusif du superviseur. Une qualification réelle et un parcours d'enrôlement isolé restent requis. Rollback : revert de la PR sans toucher aux volumes ni aux services.
