# V234-F6 — Empreinte canonique Docker

Le module collecte deux observations du daemon Docker local, valide exactement la première observation avec le contrôle V234-C puis compare leurs représentations JSON canoniques. Il retourne uniquement les identités et l'empreinte SHA-256 séparée par domaine; les secrets de configuration restent en mémoire. Les tests utilisent des observations simulées.

Cette empreinte concerne exclusivement le conteneur de revue verrouillé, pas encore le conteneur exécutable final. Elle ne doit pas être substituée à une mesure runtime finale dans un permis V2. La collecte hôte/volume, la politique complète de configuration, le contrôle des courses et le superviseur de lancement restent à intégrer. Les empreintes de configurations contenant des secrets doivent rester privées.

Tests : `python -m unittest test_prod_private_runtime_measurement`. Rollback : revert du code, aucun changement des volumes ou services.
