# V234-F4 — Contrat runtime V2

Le vérificateur Ed25519 impose un domaine distinct du permis V233 et neuf identités mesurées indépendamment : commit, digest manifeste, ID image, ID conteneur, configuration, runtime, preuves, volume et hôte. Durée maximale dix minutes, horloge UTC réelle, nonce obligatoire. Il ne délivre aucune capacité de démarrage.

Les empreintes doivent provenir du superviseur de confiance, jamais du payload signé lui-même. La collecte canonique du runtime, la définition stable des identités hôte et volume, le registre anti-rejeu V2 et la liaison au point d'entrée restent à intégrer. Le registre V233 ne valide pas ce nouveau domaine. Aucun conteneur ou serveur ne démarre.

Tests : `python -m unittest test_prod_private_runtime_contract`. Rollback : revert de la PR sans modifier les volumes, les registres ni les autres services.
