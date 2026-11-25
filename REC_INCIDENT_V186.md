# V186 — Etat persistant des incidents du monitor REC

Cette phase ajoute un moteur local indépendant du transport SMTP. Il accepte exclusivement un rapport JSON complet du monitor REC existant (six contrôles). Un incident est OPEN à la première observation en échec; CHANGED si les contrôles en échec changent; REMINDER au bout de 3600 secondes depuis le dernier événement si l'incident persiste; RECOVERED après un rapport complet PASS; NONE sinon. Intervalle proposé à valider. Une observation absente ou invalide n'est jamais un retour à la normale.

Sur un hôte de qualification, créer un répertoire privé 0700 et un rapport de test 0600. Exécuter:

    python3 scripts/rec_incident_state.py --monitor-report /private/monitor.json --state-dir /private/incidents

Etat JSON privé 0600, verrou exclusif, écriture atomique, refus des liens symboliques et des horloges régressives. Les événements sont des décisions locales, pas des accusés de réception SMTP. Le moteur ne lance aucune commande systemd, ne lit aucun secret et n'envoie aucun message. Aucun remplacement du monitor ou du mécanisme OnFailure existant. Ne pas injecter de rapports synthétiques dans un état opérationnel.

Tests : python3 -m unittest -v test_rec_incident_state. Prochaine phase : raccordement contrôlé du collecteur, gestion de la fraîcheur et de la provenance des observations, outbox durable avec acquittement de livraison SMTP et reprise après échec, surveillance distincte des services B2 quotidiens, puis qualification réelle. Le moteur actuel ne garantit pas une livraison ni une déduplication distribuée. Aucun changement des unités existantes, des timers ou de PROD. Ne pas déployer dans le répertoire actif avant qualification V179 du 26 novembre.
