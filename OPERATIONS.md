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

## V36 — ClamAV REC, socket Unix privé

Avant toute installation, vérifier la RAM disponible et si clamd existe déjà : `free -h`, `systemctl status clamav-daemon`, `ls -ld /run/clamav; ls -l /run/clamav/clamd.ctl`. Ne pas modifier un démon partagé sans revue. Le socket doit être accessible au groupe numérique du socket et le dossier traversable. Aucun port TCP ClamAV ne doit être exposé. Vérifier que les signatures sont à jour. Si absent, prévoir installation et capacité RAM avant activation.

Avec un démon hôte opérationnel, renseigner dans le .env REC (sans afficher les secrets) DSIG_CLAMD_HOST_DIR=/run/clamav et DSIG_CLAMD_GID avec le résultat de `stat -c %g /run/clamav/clamd.ctl`. Vérifier que le socket a les permissions groupe nécessaires, sans chmod global. L'overlay monte le dossier en lecture seule et ajoute uniquement ce groupe au service DSIG.

```bash
docker compose -p dsig-rec -f compose.yaml -f compose.rec-edge.yaml -f compose.rec-clamav.yaml config --quiet
docker compose -p dsig-rec -f compose.yaml -f compose.rec-edge.yaml -f compose.rec-clamav.yaml build && docker compose -p dsig-rec -f compose.yaml -f compose.rec-edge.yaml -f compose.rec-clamav.yaml up -d --no-build --wait
docker exec dsig-rec-dsig-1 python check_antivirus.py
docker exec dsig-rec-dsig-1 python preflight.py
```

Le contrôle envoie un contenu anodin et la chaîne de test standard EICAR non exécutable, uniquement au scanner privé sans enregistrer de document. Les deux résultats doivent être PASS ; la présence du socket seule ne suffit pas. En cas d'indisponibilité, le mécanisme de dépôt existant reste fail-closed. Conserver l'overlay dans toutes les commandes suivantes. Aucun GO PROD.

## V37 — Supervision locale REC

Sur le VPS, sous ubuntu : `python3 scripts/monitor-rec.py`. Le rapport vérifie conteneur, santé API, disponibilité DB indirecte via ready, scan antivirus sain, présence d'une archive privée récente (26 h), et espace disque (15 % libre). La fraîcheur n'est pas une preuve de restauration ; conserver les exercices V35.

Après validation manuelle, ajouter au crontab ubuntu sans remplacer les tâches existantes :

```cron
*/5 * * * * /usr/bin/python3 /home/ubuntu/datasphereinnovation-guinee/scripts/monitor-rec.py 2>&1 | /usr/bin/logger -t dsig-rec-monitor
```

Consulter `journalctl -t dsig-rec-monitor --since today`. FAIL est une alerte dans le journal, pas une notification externe. Une surveillance externe et l'acheminement des alertes restent nécessaires pour PROD. Aucun port supplémentaire, aucune tâche installée automatiquement.

## V40 — Ordonnancement systemd REC

Option recommandée à la place des deux entrées cron V35/V37 (ne pas cumuler). Vérifier `crontab -l` et supprimer uniquement les anciennes lignes DSIG correspondantes si présentes, après sauvegarde du crontab. Les services utilisent ubuntu et le répertoire privé existant, le même conteneur, aucune modification des autres applications. Les échecs restent visibles dans systemd et le journal ; aucune notification externe n'est activée. Les unités ne sont pas installées automatiquement.

Après validation manuelle de V35/V37, installer les quatre fichiers explicites :

```bash
cd /home/ubuntu/datasphereinnovation-guinee
sudo systemd-analyze verify deploy/systemd/dsig-rec-{backup,monitor}.{service,timer}
sudo install -m 644 deploy/systemd/dsig-rec-{backup,monitor}.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start dsig-rec-backup.service
sudo systemctl start dsig-rec-monitor.service
sudo systemctl enable --now dsig-rec-backup.timer dsig-rec-monitor.timer
systemctl list-timers 'dsig-rec-*' --all
sudo journalctl -u dsig-rec-backup.service -u dsig-rec-monitor.service -n 50 --no-pager
```

Sauvegarde à 02:15 UTC (03:15 Paris en hiver, 04:15 en été, 02:15 Guinée), rattrapage après arrêt. Monitoring toutes les cinq minutes. Examiner les statuts et les logs, notamment les FAIL ; transmettre les alertes à un canal externe approuvé et conserver une copie hors VPS. Aucune suppression automatique d'archives. Pour rollback : `sudo systemctl disable --now dsig-rec-backup.timer dsig-rec-monitor.timer`, sans toucher aux volumes ni aux autres services. Ne pas activer PROD.


## V75 — Dossier de recette et décision de mise en service

Référence de départ : PR 74 fusionnée, commit main `e72cc2ef09c415656ca35c3b8db3f9351996475e`, CI PR run 44895423283 : quatre jobs réussis (Python 3.10/3.12, navigateur, Docker). Cette preuve porte sur V74, pas sur les modifications suivantes ni sur le VPS. Pour chaque candidate, consigner le nouveau SHA et le lien de son run CI.

| Domaine | Preuve attendue pour la candidate | État terrain initial |
|---|---|---|
| Non-régression | Quatre jobs CI réussis sur le SHA exact | À confirmer |
| Site vitrine FR/EN | Navigation, expertise, formulaire et rendu mobile | À confirmer en REC |
| CRM et Supply Chain | Catalogue privé, opportunité, organisation, diagnostic sans persistance | À confirmer en REC |
| Recrutement et missions | Profil, affectation, CRA, contrat et renouvellement fictifs | À confirmer en REC |
| Finance | Devis, échéance, règlement, dépense, marges, export et rapprochement fictifs | À confirmer en REC |
| Identité | Neuf rôles, MFA, accès refusés, session révoquée | À confirmer en REC |
| GED | Dépôt et lecture, refus antivirus, indisponibilité fail-closed sur clamd réel | À confirmer en REC |
| Exploitation | TLS, accès restreint, health/ready, logs, sauvegarde hors site, restauration applicative isolée | À confirmer en REC |
| Gouvernance | Politique de rétention, sécurité indépendante, validation métier et décision signée | À confirmer |

Ne jamais utiliser de données clients réelles pendant cette recette. Renseigner pour chaque ligne : date UTC, SHA, environnement, responsable, résultat PASS/FAIL/NOT_RUN, lien vers la preuve expurgée, anomalie et action. Les résultats non exécutés ne sont pas des succès. Toute anomalie bloquante ou contrôle obligatoire non exécuté impose NO GO. La V75 renforce les tests navigateur des routes privées anonymes, sous-routes CRM/finance/missions et de la révocation après déconnexion. Elle ne débloque pas le mode PROD.

### Ordre de validation

1. Exécuter la CI et la suite isolée existante sur la candidate.
2. Déployer uniquement dans REC contrôlée, après validation de la version et sauvegarde (procédures précédentes), sans modifier les autres services.
3. Exécuter la recette fonctionnelle par rôle, le contrôle préalable, le scanner réel et l'exercice de restauration isolée.
4. Documenter les écarts, corriger en branche dédiée, rejouer les contrôles et faire valider les résultats par les responsables.
5. Une décision de production nécessite une version dédiée, revue de sécurité et autorisation humaine explicite. Aucun passage automatique en PROD.


## V76 — Preuve de version REC effectivement exécutée

PR 75 fusionnée et CI 44897596443 réussie. Pour la prochaine version approuvée, depuis le dépôt Git sur le VPS, sans modifier le conteneur actif :

```bash
cd /home/ubuntu/datasphereinnovation-guinee
git fetch origin main
python3 scripts/verify-rec-release.py "$(git rev-parse origin/main)"
docker exec dsig-rec-dsig-1 python preflight.py
python3 scripts/monitor-rec.py
```

Le premier contrôle compare les empreintes SHA-256 de tous les fichiers applicatifs copiés par le Dockerfile (Python racine, requirements.txt, dist/) au commit exact, y compris fichiers absents ou supplémentaires. Il exige REC et un conteneur healthy. La sortie JSON contient un horodatage, le SHA, le nombre de fichiers et les statuts, sans secrets ni contenu de fichiers. Git fetch ne fusionne pas et aucun conteneur n'est redémarré. Utiliser uniquement un SHA dont la CI est verte ; la commande ne vérifie pas elle-même GitHub Actions. Le contrôle est testé sur le conteneur CI. Un écart impose de revoir la version candidate avant promotion. Il ne prouve ni la provenance de l'image de base, ni les versions exactes des dépendances installées, ni la configuration TLS ou les données ; la recette métier, l'antivirus réel, les sauvegardes et l'autorisation humaine restent obligatoires. Aucun GO PROD automatique.
