# V187 — Outbox persistante des alertes REC

Le nouveau programme collecte directement les six contrôles du monitor existant. L'observation et l'enregistrement d'un événement sont dans la même transaction SQLite. La livraison est une commande distincte, explicite, qui traite un événement à la fois dans l'ordre. Echec SMTP: nouvelle tentative au plus tôt cinq minutes plus tard. Succès: état SMTP_ACCEPTED (pas une preuve de réception dans la boîte). Un Message-ID stable aide à identifier les doublons, sans garantie exactly-once: interruption entre acceptation SMTP et commit peut entraîner un renvoi. Les événements acceptés sont conservés; une politique de rétention est à définir. Maximum 1000 événements non acceptés; saturation en échec explicite sans avancer l'état de l'incident.

Qualification sur hôte REC isolé, répertoire dédié 0700 et fichiers privés. Ne pas utiliser le fichier incident.json V186: V187 possède son propre état transactionnel. Ne pas exposer de secrets dans la commande, les journaux ou Git.

    python3 scripts/rec_alert_outbox.py --state-dir /private/outbox --observe

La commande --deliver (même répertoire) effectue un envoi réel avec les variables SMTP existantes; ne l'exécuter qu'après approbation du destinataire de test et configuration privée. Les tests utilisent un transport simulé. Ne pas lancer sur le VPS actif avant le cycle V179. Aucun service systemd ou timer modifié par cette PR; les alertes OnFailure restent intactes. Prochaine phase: unités séparées de collecte/livraison, supervision des échecs de collecte, incidents B2, politique de rétention et qualification SMTP réelle. L'absence d'observation ne vaut pas récupération. L'état n'est pas partagé entre plusieurs hôtes. Aucun GO PROD.

    python3 -m unittest -v test_rec_alert_outbox
