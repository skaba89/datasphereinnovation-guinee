# V166 — Rapport de direction en ligne (CSV / PDF)

Page `rapport.html`, accessible depuis **Pilotage** (lien « Rapport hebdomadaire (CSV / PDF) »).

- Mêmes indicateurs que l'e-mail du lundi (V163) : activité, pipeline, demandes par besoin, points d'attention.
- Navigation semaine par semaine ; par défaut, les 7 derniers jours **y compris aujourd'hui**.
- **Exporter CSV** : fichier `rapport-direction-<semaine ISO>.csv` (séparateur `;`, UTF-8 avec BOM, cellules commençant par `= + - @` neutralisées).
- **Imprimer / PDF** : mise en page d'impression dédiée (menus et boutons masqués) ; choisir « Enregistrer au format PDF » dans la boîte d'impression du navigateur.

## API

`GET /api/admin/direction/weekly-report?date=AAAA-MM-JJ[&format=csv]` — permission `direction` en lecture.
La date est la fin de période (exclue). Les rôles sans lecture CRM (ex. AUDITEUR) reçoivent le nombre de relances en retard, sans le nom des sociétés.
Aucune donnée de contact (nom, e-mail, message) n'est exposée. Lecture seule, réponse `Cache-Control: no-store`.

## Vérification

```bash
python -m unittest test_weekly_report
python -m pytest browser_e2e.py -k weekly_report_page
```
