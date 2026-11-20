# Exploitation et continuité de recette locale

Ces procédures utilisent uniquement des données fictives. La recette HTTPS peut être accessible sur une liste d’IP autorisées. Le mode PROD reste bloqué.

## Recette derrière un reverse proxy HTTPS

`DSIG_HTTPS_ORIGIN=https://rec.dsig-consulting.com` (sans slash final) active l'origine HTTPS exacte et les cookies Secure. Sans cette variable, le fonctionnement HTTP local est inchangé. Le serveur ne fait confiance à aucun en-tête X-Forwarded-* pour déterminer l'origine. Le proxy doit préserver Host et terminer TLS. Les sondes GET /api/health et /api/ready restent accessibles en interne. Le port Docker doit rester lié à loopback et le réseau backend privé ; ne pas publier le port Python. En mode HTTPS les pages ne sont plus accessibles avec Host localhost, ce qui est intentionnel.

Avant de publier une recette, limiter l'accès au proxy avec une liste d'IP autorisées ou un VPN dédié, en conservant Authorization pour le Bearer DSIG (ne pas superposer Basic Auth). Ne pas modifier la protection des autres sites. Les limites de débit actuelles sont par IP du proxy, pas par IP cliente ; aucun en-tête client ne doit être considéré comme fiable sans configuration dédiée. Valider TLS, contrôle des origines, activation, connexion, MFA et révocation dans la vraie recette avant d'utiliser des données réelles. Aucun mode PROD n'est autorisé par cette configuration.

## Sauvegarde et restauration (PowerShell)

1. Installer les dépendances : `python -m pip install -r requirements.txt`.
2. Générer **une seule fois** une clé indépendante de la clé MFA : `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Conserver la valeur dans un coffre et charger `DSIG_BACKUP_KEY` dans l'environnement local. Conserver aussi `DSIG_MFA_KEY` séparément ; son absence empêche la vérification MFA après restauration.
3. Créer un dossier privé `backups` hors du répertoire web, puis lancer :

```powershell
python server.py --check-db
python server.py --backup-encrypted backups/recette-20261120.dsigbak
python server.py --restore-isolated backups/recette-20261120.dsigbak backups/restore-20261120.sqlite3
```

Les destinations doivent être nouvelles. La restauration refuse la base active et le répertoire `dist`. Le contrôle de schéma et `PRAGMA integrity_check` sont effectués avant et après révocation des sessions restaurées. Le fichier restauré est en clair ; il doit rester protégé et être éliminé selon les règles de conservation. Les fichiers temporaires de travail sont en clair dans un dossier privé ; cette procédure ne garantit pas l'effacement physique des supports. La limite du mode Fernet est de 64 Mio de base SQLite (chiffrement en mémoire).

Pour tester l'application restaurée dans une instance distincte, ouvrir un autre terminal, charger les clés depuis le coffre, définir `DSIG_DB` vers le fichier restauré puis `python server.py --port 8082`. Ne pas remplacer la base active. Vérifier les comptes, une demande fictive, une mission et les totaux financiers ; les utilisateurs doivent se reconnecter. Ne pas restaurer une archive non vérifiée sur la recette active.

## Supervision et objectif de continuité

- `/api/health` : vivacité HTTP, sans détail interne.
- `/api/ready` : base accessible avec schéma attendu ; 503 si indisponible. Ne réalise ni contrôle complet d'intégrité à chaque appel ni test d'écriture.
- `python server.py --check-db` : intégrité complète, à exécuter hors période de charge importante.
- Docker : `docker compose ps` ; consulter les logs en cas d'état unhealthy. Le healthcheck utilise `/api/ready`.
- Cibles de recette proposées, à mesurer : sauvegarde quotidienne (RPO cible 24 h), exercice de restauration mensuel (RTO cible 2 h), conservation 7 archives quotidiennes et 4 hebdomadaires hors serveur. Aucun ordonnanceur, service d'alerte ou stockage distant n'est configuré à ce stade.
- Journaliser chaque exercice (date, environnement, résultat, durée, écarts) sans secret ni données personnelles. Vérifier l'espace disque et l'accès aux clés. Une sauvegarde non restaurée avec succès ne vaut pas preuve de reprise.

En production : sauvegardes hors site, rétention formalisée, chiffrement des volumes, supervision centralisée et alertes, rotation des clés, tests de restauration représentatifs, revue indépendante et objectifs de service approuvés restent nécessaires. Avant toute promotion d'une restauration, réconcilier les comptes désactivés, mots de passe, MFA et codes de secours depuis la date de l'archive : un retour dans le temps peut rétablir des secrets ou codes déjà utilisés. Cette procédure n'autorise pas la promotion automatique.

## Exercice de restauration isolée — VPS OVHCloud, recette HTTPS

Ne pas remplacer la base active. Les commandes supposent le conteneur de recette déjà démarré et les clés existantes chargées dans son environnement, sans les afficher. Le fichier restauré est en clair dans le tmpfs du conteneur ; ne pas le copier vers l'hôte.

```bash
cd /home/ubuntu/datasphereinnovation-guinee
(
  set -euo pipefail
  umask 077
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  c=dsig-rec-dsig-1
  archive="/tmp/dsig-rec-${stamp}.dsigbak"
  restored="/tmp/dsig-restore-${stamp}.sqlite3"
  mkdir -p -m 700 "$HOME/dsig-backups"
  destination="$HOME/dsig-backups/dsig-rec-${stamp}.dsigbak"
  test ! -e "$destination"
  docker exec "$c" python server.py --check-db
  docker exec "$c" python server.py --backup-encrypted "$archive"
  docker exec "$c" python server.py --restore-isolated "$archive" "$restored"
  docker exec "$c" cat "$archive" > "$destination"
  test -s "$destination"
  test "$(docker exec "$c" sha256sum "$archive" | cut -d' ' -f1)" = "$(sha256sum "$destination" | cut -d' ' -f1)"
  chmod 600 "$destination"
  sha256sum "$destination"
  docker exec "$c" rm -- "$archive" "$restored"
  curl -fsS http://127.0.0.1:8300/api/ready
)
```

En cas d'erreur, arrêter l'exercice, identifier le fichier temporaire exact avant nettoyage et conserver les journaux sans secrets. Le résultat prouve l'intégrité et la restauration isolée, mais pas une reprise applicative complète. Conserver une copie chiffrée hors VPS et les clés séparément. Ne jamais utiliser `docker compose down -v`.

### Critères GO/NO GO avant production

- [ ] Vérifier le commit et les tests CI de la version effectivement déployée.
- [ ] Vérifier TLS, accès REC autorisé / refusé, MFA et séparation des rôles.
- [ ] Parcourir les modules métier avec données fictives, y compris exports CSV.
- [ ] Exécuter l'exercice de sauvegarde/restauration, mesurer les durées et tester une instance restaurée isolée.
- [ ] Confirmer la supervision, les clés, les sauvegardes hors site, l'antivirus et la capacité du VPS.
- [ ] Lever explicitement les blocages PROD dans une version dédiée, après revue de sécurité et validation humaine.

## V34 — Contrôle préalable REC

Après déploiement, exécuter `docker exec dsig-rec-dsig-1 python preflight.py`. Le rapport JSON ne contient aucune valeur secrète. FAIL retourne 1 ; WARN (socket antivirus absent) retourne 0 mais exige une action. PASS ne vaut pas autorisation de production. Vérifier séparément HTTPS et restriction d'accès, connexion MFA réelle, scan antivirus, restauration isolée et recette métier. Le contrôle SQLite utilise une connexion en lecture seule.

## V35 — Sauvegarde quotidienne REC (Linux)

Exécuter manuellement depuis le VPS : `bash scripts/backup-rec.sh`. Verrouillage, restauration isolée, transfert via docker exec compatible tmpfs, comparaison SHA256 et publication sans écrasement. Aucun effacement d'archives historiques, aucun GO PROD.

Après un premier succès réel, ajouter au crontab ubuntu (sans remplacer les tâches existantes) :

```cron
15 2 * * * /bin/bash /home/ubuntu/datasphereinnovation-guinee/scripts/backup-rec.sh >> /home/ubuntu/dsig-backups/backup.log 2>&1
```

Prévoir rotation du journal, surveillance d'espace, alertes et externalisation chiffrée. Le cron utilise le fuseau du VPS. Ne jamais stocker les clés avec les archives. Aucune tâche cron installée automatiquement.
