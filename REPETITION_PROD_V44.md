# V44 — Répétition isolée de la future production

Le fichier compose.prod-candidate.yaml est une configuration indépendante en mode REC. Aucun accès public, aucune connexion au réseau edge, aucune modification Caddy ni DNS. Le serveur conserve son verrou PROD. Le volume candidate-data est neuf et distinct ; ne jamais y importer les données réelles.

## Préparer le VPS

Vérifier que le port 8310 est libre (`sudo ss -tlnp`) et que les ressources restent suffisantes. Créer un fichier privé hors dépôt, mode 0600, par exemple /home/ubuntu/dsig-candidate.env. Générer quatre clés distinctes et différentes de celles de REC à partir d'un générateur cryptographique. ADMIN : token URL-safe de 48 octets ; MFA/BACKUP/DOCUMENT : clés Fernet. Ne jamais afficher ni recopier des clés dans les logs. Renseigner les variables DSIG_CANDIDATE_ADMIN_TOKEN, DSIG_CANDIDATE_MFA_KEY, DSIG_CANDIDATE_BACKUP_KEY, DSIG_CANDIDATE_DOCUMENT_KEY et DSIG_CLAMD_GID (identifiant numérique du groupe socket existant).

```bash
cd /home/ubuntu/datasphereinnovation-guinee
docker compose --env-file /home/ubuntu/dsig-candidate.env -p dsig-prod-candidate -f compose.prod-candidate.yaml config --quiet
docker compose --env-file /home/ubuntu/dsig-candidate.env -p dsig-prod-candidate -f compose.prod-candidate.yaml up -d --build --wait
docker compose --env-file /home/ubuntu/dsig-candidate.env -p dsig-prod-candidate -f compose.prod-candidate.yaml ps
curl -fsS http://127.0.0.1:8310/api/ready
docker exec dsig-prod-candidate-candidate-1 python preflight.py
docker exec dsig-prod-candidate-candidate-1 python check_antivirus.py
```

L'origine candidate.invalid sert uniquement à vérifier la configuration HTTPS ; aucun certificat, accès HTTPS ou test navigateur réel n'est fourni par cette répétition. Pour arrêter : utiliser la même commande Compose avec stop, sans supprimer les volumes. Aucun GO PROD. Terminer les gates V39 avant toute release publique.
