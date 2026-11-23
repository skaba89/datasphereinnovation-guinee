# V167 — Tâches commerciales

Page `taches.html` (menu « Tâches commerciales », rôles ayant accès au CRM).

- **Ma journée** : tâches en retard, du jour, à venir ; compteurs « en retard », « du jour », « à 7 jours ».
- Types : appel, e-mail, relance, rendez-vous, autre. Rattachement facultatif à une opportunité ouverte (lien vers la fiche client si l'organisation est liée).
- Création en un clic depuis le Kanban : lien **« + Tâche »** sur chaque opportunité ouverte (opportunité présélectionnée).
- Actions rapides : **Fait**, **Demain**, **+7 j**, **Annuler**. Vue « Toute l'équipe » et historique des tâches terminées.
- Les tâches en retard alimentent le centre de notifications (`TACHE_EN_RETARD`, URGENT) à chaque `--refresh-notifications`.

## Règles

| Rôle | Droits |
|---|---|
| COMMERCIAL | Crée des tâches pour lui, un collègue commercial/admin ou non attribuées ; modifie les siennes et les non attribuées |
| ADMIN | Tous les droits |
| DIRECTION | Lecture seule |
| Autres rôles sans CRM | Aucun accès |

Verrouillage optimiste par version (409 si la tâche a changé entre-temps). Journal d'audit : `TACHE_CREEE`, `TACHE_REPORTEE`, `TACHE_TERMINEE`, `TACHE_ANNULEE`.

## API

- `GET /api/admin/crm/tasks?view=mine|team&state=open|done`
- `POST /api/admin/crm/tasks` `{title, kind, due_date, opportunity_id, owner_id}` (`owner_id`: `me`, `''` ou identifiant de compte)
- `PATCH /api/admin/crm/tasks/<id>` `{status: FAIT|ANNULEE, version}` ou `{due_date, version}`

## Vérification

```bash
python -m unittest test_crm_tasks
python -m pytest browser_e2e.py -k commercial_tasks
```
