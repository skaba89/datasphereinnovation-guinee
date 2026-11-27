# V234-F11 — Émetteur et destinataire du permis

L'émetteur vérifie la clé Ed25519 contre l'empreinte de confiance, valide le contrat V2, réserve le nonce dans le registre durable puis signe une réponse liée au défi du destinataire. Toute panne après réservation brûle le permis; aucune réémission automatique. Le destinataire ferme son défi dès la première tentative de vérification, sous verrou thread-safe.

Tests : `python -m unittest test_prod_private_handoff_issuer`. Les tests utilisent des clés synthétiques et un registre SQLite temporaire. Les empreintes attendues sont des fixtures, pas des mesures Docker finales. La clé privée doit rester côté hôte et être protégée indépendamment. Le transport authentifié, la mesure de la topologie exécutable, le provisionnement de confiance et le point d'entrée métier restent à intégrer. Le résultat PASS ne constitue pas une autorisation de démarrage.

Rollback : revert du code, conserver le registre de nonces. Aucun changement du VPS, de Compose ni des verrous PROD.
