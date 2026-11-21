# V78 — Contrôle de configuration avant activation REC

Contrôle en lecture seule, à exécuter avant activation et après modification des overlays. Aucun démarrage ni déploiement. La configuration résolue contient potentiellement des secrets : ne jamais l'afficher, la sauvegarder ou la joindre à un ticket. Utiliser un pipe direct et `set -o pipefail`.

## REC existante

Vérifier indépendamment le nom du volume actif monté sur /app/data, par exemple :

```bash
docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Name}}{{end}}{{end}}' dsig-rec-dsig-1
```

Reprendre **exactement** les fichiers Compose utilisés par le service actuel (y compris les overlays privés et l'overlay de release prévu), dans leur ordre réel. Exemple uniquement avec base et antivirus :

```bash
set -o pipefail
docker compose -p dsig-rec -f compose.yaml -f compose.rec-clamav.yaml config --format json | python3 verify_rec_config.py --profile rec --volume dsig-rec_dsig-data
```

Remplacer le volume d'exemple par la valeur indépendamment vérifiée. Ne pas ajouter ou retirer des overlays pour obtenir PASS. Le port doit rester loopback, le mode REC, le volume identique, la racine en lecture seule, les capacités supprimées et le socket antivirus monté en lecture seule. Les sorties ne contiennent que les statuts.

## Candidate indépendante

```bash
set -o pipefail
docker compose -f compose.prod-candidate.yaml config --format json | python3 verify_rec_config.py --profile candidate --volume dsig-prod-candidate_candidate-data
```

Les secrets candidats doivent être dédiés. Confirmer séparément les réseaux, la source exacte du bind scanner (répertoire privé ClamAV, permissions et socket réel), la publication TLS, l'utilisateur de l'image et son identifiant. Un PASS ne vérifie pas la configuration du proxy, le contenu du volume, la provenance de l'image ou les droits du socket. Les tests Python couvrent configurations valides, volume incorrect, port public, mode PROD, hôte privilégié et autres cas de refus. Rejouer V75/V76/V77 et maintenir NO GO PROD jusqu'à validation humaine.
