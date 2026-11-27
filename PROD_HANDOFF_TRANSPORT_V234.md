# V234-F12 — Transport du permis

Protocole Unix socket à échange unique, contrôle Linux SO_PEERCRED du UID attendu, trames JSON préfixées et limitées à 16 KiB, lecture avec délai monotone de cinq secondes, rejet des doublons JSON, fermeture systématique. Le superviseur émet seulement après réservation durable du nonce; le destinataire vérifie la réponse signée et son défi.

Tests sur de véritables sockets locaux avec clés synthétiques et registre temporaire : `python -m unittest test_prod_private_handoff_transport`. Le UID seul ne prouve pas l'identité Docker : il faut encore un socket dédié protégé, vérifier la provenance du processus et son rattachement au conteneur, provisionner les références de confiance et mesurer la topologie exécutable. Aucun démarrage métier n'est autorisé. Le test socketpair ne qualifie pas les namespaces Docker.

Rollback : revert du code, préserver les registres et les services existants.
