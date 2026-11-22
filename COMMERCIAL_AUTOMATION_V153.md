# V153 — Automatisations commerciales internes

Le traitement `python server.py --refresh-notifications` complète les rappels commerciaux existants : abonnements SaaS à renouveler sous 30 jours ou échus, factures SaaS proches de leur échéance ou impayées. Les renouvellements enregistrés, résiliations et factures soldées disparaissent des alertes actives sans supprimer leur historique. Aucun email, SMS, prélèvement ou renouvellement automatique.

Le module Notifications (ADMIN et DIRECTION selon les autorisations existantes) expose les dix derniers traitements : date UTC, PASS/FAIL, nouvelles notifications et volume actif. Un échec transactionnel conserve l'état antérieur ; son journal ne contient pas les détails sensibles de l'exception. Une panne de stockage peut empêcher l'écriture du journal ; le statut du service reste alors la référence.

Après qualification et déploiement REC de cette version, vérifier l'absence de planification existante du même traitement. Les unités optionnelles `dsig-rec-notifications.service` et `.timer` peuvent être installées par l'opérateur : traitement quotidien à 08:00 UTC, conteneur REC uniquement. Tester le service manuellement avant d'activer le timer. Ne pas cumuler avec cron. Pour arrêter la planification : `sudo systemctl disable --now dsig-rec-notifications.timer`. Aucun changement automatique du VPS ni GO PROD.
