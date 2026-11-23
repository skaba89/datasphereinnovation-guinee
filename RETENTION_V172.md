# V172 — Conservation et suppression des données des demandes de contact

Prérequis du formulaire public (issue #156, point « politique de conservation et suppression vérifiable »).

## Règle de conservation (à valider juridiquement)

Une demande est **anonymisée automatiquement** lorsqu'elle :

- n'a **pas** été qualifiée en opportunité CRM (aucune relation commerciale établie) ;
- n'a connu **aucune activité** (création, changement de statut, note de suivi) depuis `DSIG_REQUEST_RETENTION_DAYS` jours.

Valeur par défaut : **1095 jours (3 ans)**, bornée entre 30 et 3650. Cette durée est une **proposition technique** : elle doit être confirmée par la revue juridique (champ `email_retention` de V161) avant toute donnée réelle.

## Ce que fait l'anonymisation

- Supprimés : nom, organisation, e-mail, message, solution ; notes libres du suivi ; destinataires mémorisés ; e-mails encore en attente (annulés).
- Prospect CRM créé automatiquement **encore au stade PROSPECT** : contact, e-mail et notes effacés.
- Conservés (statistiques, sans donnée personnelle) : identifiant, date, type de besoin, statut.
- Une relation commerciale réelle (opportunité qualifiée, client) n'est **pas** touchée par la purge automatique.
- Audit : `DEMANDE_ANONYMISEE` avec l'identifiant et le motif, sans donnée personnelle. Idempotent.

## Commandes

```bash
python server.py --purge-requests           # aperçu : nombre de demandes concernées, rien n'est modifié
python server.py --purge-requests --apply   # anonymisation
```

## Droit à l'effacement

`POST /api/admin/requests/<id>/erase` — **ADMIN uniquement** : anonymisation immédiate d'une demande (même qualifiée), réponse `ANONYMISEE` ou `DEJA_ANONYMISEE`. Les données d'une opportunité qualifiée ou d'un client restent à traiter selon la procédure de la relation contractuelle.

## Planification (non installée)

`deploy/systemd/dsig-rec-retention.{service,timer}` : le 1er de chaque mois à 03:30 UTC. **N'installer qu'après validation juridique de la durée** et un aperçu vérifié :

```bash
sudo systemd-analyze verify deploy/systemd/dsig-rec-retention.{service,timer}
sudo install -m 644 deploy/systemd/dsig-rec-retention.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now dsig-rec-retention.timer
```

## Correction associée

`server.connect()` valide désormais l'initialisation du schéma. Auparavant, sur une base n'ayant encore servi aucune requête, l'insertion des modèles d'e-mails par défaut (V168) laissait une transaction ouverte : les commandes planifiées (`--refresh-notifications`, `--automation-preview`) échouaient avec « cannot start a transaction within a transaction ».

## Vérification

```bash
python -m unittest test_retention
```
