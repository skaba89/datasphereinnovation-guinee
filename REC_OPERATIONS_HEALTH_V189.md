# V189 — Diagnostic opérationnel REC en lecture seule

Le diagnostic contrôle la dernière observation, les checks du monitor, le quick_check SQLite de l'outbox, l'ancienneté de la file et son niveau de saturation. Seuils proposés : 15 minutes pour observation et attente, WARN à 80% de 1000 événements, FAIL à saturation. Compte les événements SMTP acceptés depuis plus de 90 jours sans supprimer aucune donnée. La politique de rétention doit être approuvée avant implémentation.

Contrôle B2 local : après 04:20 UTC (04:05 + délai de téléchargement + marge), exige l'archive unique du jour entre 02:00 et 03:00 et sa preuve scheduled V185 horodatée entre 03:00 et 04:00 UTC, avec SHA256 conforme. Avant cette échéance, contrôle le cycle précédent. Les preuves manuelles et historiques sont exclues. Il ne vérifie ni le journal systemd ni la présence actuelle de l'objet distant; l'audit B2 réel reste obligatoire. Un PASS est un diagnostic local et non un GO PROD.

    python3 scripts/rec_operations_health.py --state-dir /var/lib/dsig-rec-outbox --backups /home/ubuntu/dsig-backups --proofs /home/ubuntu/dsig-b2-automation

Codes: PASS=0, FAIL=1, WARN=2. Aucun secret, envoi SMTP, création de base ou purge. Exécuter comme propriétaire des répertoires privés. Les erreurs ou données absentes ne sont pas considérées saines. Les seuils sont à valider en exploitation. Tests synthétiques: python3 -m unittest -v test_rec_operations_health. Aucun timer ajouté. Ne pas déployer avant la qualification du cycle V179 du 26 novembre, puis qualifier V185 et V188 indépendamment. La surveillance distante et l'alerte sur la défaillance du diagnostic restent à intégrer.
