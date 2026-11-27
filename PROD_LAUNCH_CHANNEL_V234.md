# V234-F10 — Remise cryptographique du permis

Le vérificateur impose un défi aléatoire de 256 bits, une réponse signée Ed25519 liée à l'enveloppe V2 complète et au conteneur, et une validité maximale de 60 secondes limitée par le permis V2. Aucun secret privé n'est inclus dans le conteneur par ce module.

Le défi doit être généré et conservé par le processus destinataire, consommé une seule fois par celui-ci. Ce module ne gère pas l'état de consommation du défi. L'émetteur de la réponse doit vérifier la réservation durable et les mesures finales avant signature. La signature seule ne prouve pas la réservation. Le canal de transport, le provisionnement indépendant de la confiance, l'émetteur et le point d'entrée restent à implémenter; aucune autorisation de lancement n'est délivrée.

Tests : `python -m unittest test_prod_private_launch_channel`. Rollback : revert du code uniquement. Les verrous et les services existants restent inchangés.
