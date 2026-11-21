# V95 — Qualification consolidée REC

La CI verte ne vaut pas recette terrain. La V95 rassemble les trois rapports existants sur le même SHA exact et maintient le verrou PROD. Aucun accès au VPS, aucune modification d'environnement, aucune preuve préremplie.

## Exécution sur la REC approuvée

Après déploiement REC contrôlé, créer un dossier de preuves privé neuf hors Git (mode 0700). Dans les commandes suivantes, remplacer `/chemin/prive` par ce dossier existant :

```bash
umask 077
sha=$(git rev-parse HEAD)
python3 scripts/rec-preflight.py "$sha" > /chemin/prive/preflight.json
python3 release_evidence.py "$sha" --template > /chemin/prive/register.json
```

Compléter les 18 déclarations du registre selon RELEASE_GATE_V79.md et les 10 gates selon PREPARATION_PROD_V39.md dans un fichier privé `gates.json` (modèle release-gates.example.json). Utiliser uniquement les preuves réelles, datées et expurgées du SHA concerné, notamment CI exacte, recette métier, MFA, refus d'accès, sauvegarde hors site, restauration, sécurité indépendante et décision humaine. Une copie locale seule ne valide pas G04. Ne pas réutiliser les résultats d'un autre SHA.

```bash
python3 scripts/qualify-release.py "$sha" \
  --preflight /chemin/prive/preflight.json \
  --register /chemin/prive/register.json \
  --gates /chemin/prive/gates.json
```

Le rapport exige un preflight technique PASS datant de moins de 24 heures, le registre complet et les dix gates complètes sur ce SHA. Il affiche les statuts individuels sans références ni identités des reviewers. NO_GO (code 1) bloque la qualification. REVIEW_REQUIRED (code 0) indique uniquement la complétude déclarative : vérifier l'authenticité et la fraîcheur de toutes les preuves séparément. `production_authorized` est toujours `false`. Aucun score de maturité ni validation légale n'est déduit automatiquement.
