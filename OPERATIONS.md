# Exploitation et continuité de recette locale

Ces procédures utilisent uniquement des données fictives. Aucun déploiement Internet. Le mode PROD reste bloqué.

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
