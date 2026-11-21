# V96 — Préparation REC sans dérive de configuration

Périmètre : `dsig-rec`, service `dsig`, port 8300, volume `dsig-rec_dsig-data`, réseaux `dsig-rec_default` et `edge`. Le candidat isolé (8310), Caddy et les autres applications ne sont pas ciblés. Aucun déploiement dans cette version.

## Avant la mise à niveau

1. Confirmer le SHA approuvé et les quatre jobs CI sur ce SHA (y compris le commit de fusion). Interdire les interventions concurrentes. Relever les identifiants actif, candidate et rollback, l'état healthy, les montages et les fichiers Compose effectivement utilisés via `docker inspect` avec un format ciblé qui ne révèle pas les secrets.
2. Avant de modifier le checkout, conserver la configuration Compose résolue de la version actuelle dans un dossier privé hors Git (mode 0700, umask 077). Vérifier sa concordance avec le conteneur réellement actif ; le fichier contient des secrets, ne jamais l'envoyer dans un chat ni le versionner.
3. Mettre à jour uniquement par fast-forward vers le SHA approuvé. Préserver `.env` et les overlays locaux. Exécuter `bash scripts/prepare-rec-upgrade.sh "$sha"` suivant OPERATIONS.md V77. Ce script ne bascule pas le service. Tester la restauration sur les deux images dans des conteneurs jetables, sans réseau ni volume actif, puis confirmer la compatibilité descendante du schéma.
4. Préparer un overlay candidat minimal hors Git, sans écraser l'overlay actif. Résoudre la configuration candidate avec les mêmes fichiers et le même projet, en substituant le seul overlay d'image. Conserver la résolution dans le dossier privé ou utiliser un descripteur de fichier Bash. Ne jamais afficher le JSON Compose brut.

## Contrôle supplémentaire

```bash
python3 scripts/check-rec-upgrade.py "$sha" \
  /chemin/prive/actuel.json /chemin/prive/candidat.json
```

Le contrôle exige des configurations REC sûres et identiques à l'exception de `services.dsig.image`, l'image `dsig-rec-candidate:<sha>`, les réseaux attendus, le port et l'origine HTTPS exacts. Il ne révèle pas les différences sensibles. Toute autre modification exige une revue séparée. Le contrôle compare les configurations déclarées, **pas** les paramètres effectifs du conteneur, ni l'identifiant réel d'une image taguée. Vérifier ces éléments séparément avant activation. Supprimer les fichiers temporaires contenant des secrets selon la politique locale après usage.

## Recette après activation humaine

Suivre OPERATIONS.md V77 et QUALIFICATION_V95.md. Vérifier le contenu déployé et les quatre contrôles preflight sur le SHA exact. Rejouer avec données fictives : création du profil consultant et compte associé, MFA et refus hors rôle, recrutement filtré au-delà de 25 résultats, parcours CRM–devis–contrat–mission–CRA–finance, encaissement partiel et solde, recherche des créances, navigation mobile et pagination. Vérifier les timers DSIG et les deux endpoints locaux. Conserver les preuves expurgées et les résultats de rollback.

NO GO PROD tant que les preuves terrain, sauvegarde chiffrée hors VPS, revue indépendante et approbation humaine restent manquantes. Aucun score de maturité ne découle du seul PASS de configuration.
