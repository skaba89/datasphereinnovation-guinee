# V42 — Notifications d'incidents REC

Option SMTP TLS implicite port 465, à activer seulement après choix du fournisseur et destinataire. Le message ne contient ni secrets ni données métier. Le journal reste la preuve locale. Aucun envoi activé par défaut. La limitation systemd réduit les répétitions à une tentative de notification par instance toutes les 30 minutes ; consulter les journaux si envoi échoué.

Créer avec sudoedit un fichier /etc/dsig-rec-alert.env possédé par root, mode 0600, avec les variables DSIG_ALERT_SMTP_HOST, DSIG_ALERT_SMTP_USER, DSIG_ALERT_SMTP_PASSWORD, DSIG_ALERT_FROM, DSIG_ALERT_TO. Utiliser un secret d'application dédié, jamais dans Git. Vérifier que les unités V40 sont installées.

Installer le fichier deploy/systemd/dsig-rec-alert@.service dans /etc/systemd/system, puis créer un drop-in pour chacune des unités dsig-rec-backup.service et dsig-rec-monitor.service :

```ini
[Unit]
OnFailure=dsig-rec-alert@%n.service
```

Exécuter systemctl daemon-reload ; vérifier systemctl cat pour chaque unité. Tester explicitement avec sudo systemctl start dsig-rec-alert@test.service et vérifier la réception réelle, pas seulement l'acceptation SMTP. Tester un incident en environnement isolé, sans arrêter la recette ni les autres applications. La notification ne détecte pas une panne totale du VPS : une supervision depuis un autre hôte est encore indispensable. Aucun GO PROD.
