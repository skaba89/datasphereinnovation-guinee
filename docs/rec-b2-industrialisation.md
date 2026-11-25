# Exploitation B2 REC

Le mode sans argument est réservé au cycle quotidien UTC : sauvegarde 02:15, export 03:00, audit 03:30. Une archive unique de 02:00 à 03:00 est exigée. Le marqueur quotidien doit être créé entre 03:00 et 04:00. Un retard ne doit pas être masqué par une preuve manuelle.

Mode manuel : `bash scripts/export-rec-b2.sh --manual --archive NOM.dsigbak` puis `python3 scripts/audit-rec-b2.py --manual --archive NOM.dsigbak`. L'export exige une archive de moins de trois heures. L'audit manuel ne certifie pas le cycle quotidien. Les marqueurs historiques restent compatibles. Si un upload a réussi sans marqueur, l'export consulte l'inventaire et vérifie le contenu distant avant de publier le marqueur, sans nouvel upload si l'objet existe. Une erreur d'inventaire est bloquante.

## Déploiement REC après CI verte et revue
Depuis /home/ubuntu/datasphereinnovation-guinee : git fetch origin, vérifier le SHA approuvé et git status, puis git merge --ff-only origin/main. Ne pas supprimer compose.rec-edge.yaml. Exécuter python3 -m unittest test_audit_rec_b2 et bash -n scripts/export-rec-b2.sh. Sauvegarder la configuration systemd existante dans un répertoire privé. Inspecter les drop-ins (notamment override.conf) : installer industrialisation.conf sous le nom zz-industrialisation.conf pour prendre priorité. sudo systemctl daemon-reload, vérifier ExecStart et OnFailure effectifs et laisser les timers inchangés. Tester le mode manuel hors fenêtre quotidienne puis observer le prochain cycle réel.

## Rollback
Retirer uniquement le nouveau drop-in zz-industrialisation.conf, recharger systemd, vérifier que ExecStart revient au script historique hors dépôt. Ne supprimer ni archives ni marqueurs. Pour l'audit, restaurer le script approuvé précédent par une nouvelle PR de revert ou un chemin de déploiement isolé ; ne pas réinitialiser main de manière destructive.

## Alertes
Conserver OnFailure et le seuil 1/30 min. Une notification SMTP acceptée ne garantit pas la réception. Un rappel périodique des incidents persistants reste à implémenter et qualifier ; la limitation systemd seule ne relance pas une notification.

## Limites
Aucun GO production. La qualification réelle du cycle, de la rétention et du PRA indépendant reste obligatoire.
