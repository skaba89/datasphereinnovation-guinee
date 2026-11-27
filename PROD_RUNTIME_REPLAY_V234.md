# V234-F5 — Registre anti-rejeu V2

Registre SQLite séparé du V233, initialisation explicite sans écrasement, fichier 0600 dans répertoire privé 0700. La consommation vérifie la signature avant puis pendant la transaction BEGIN IMMEDIATE. Le nonce et le hash du payload sont uniques, l'identité du conteneur est conservée, synchronous FULL est exigé. Aucun lancement ne résulte de cette réservation.

Tests : `python -m unittest test_prod_private_runtime_replay`. Le registre doit rester hors du conteneur, sous contrôle de l'opérateur. Un registre restauré à un état antérieur ou remplacé par un opérateur privilégié peut perdre la mémoire des nonces : ancrage externe et politique de récupération restent nécessaires. Ne jamais recréer le registre après une panne. Rollback du code uniquement, conserver le registre. Le superviseur doit réserver au dernier moment après mesures indépendantes; ne pas consommer un vrai permis avant intégration finale.
