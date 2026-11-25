# PRA V182 — préparation systemd et ClamAV

Cette phase prépare exclusivement 13 unités REC, quatre drop-ins et deux configurations ClamAV à partir du kit V2. Aucun service installé, aucun timer activé, aucune modification de /etc ni du VPS actif.

Sur un hôte de secours dédié, qualifier V2 avec V180 et une empreinte indépendante. Extraire ensuite le kit authentifié dans un répertoire privé appartenant à l'opérateur (umask 077; fichiers 0600, répertoires 0700). Ne jamais extraire une archive non vérifiée. Conserver l'extraction et le staging à l'abri de toute modification concurrente.

    mkdir -m 700 ~/pra-staging
    python3 scripts/pra_system_stage.py --source /private/v2 --private-stage-parent ~/pra-staging

Le rapport JSON identifie les 19 fichiers préparés et leurs empreintes. Les fichiers de secrets externes ne sont pas copiés. Ce programme ne valide pas la sémantique des unités ou des configurations, et ne prouve pas l'absence de secrets. Examiner manuellement les chemins, propriétaires, dépendances, permissions du socket ClamAV et directives EnvironmentFile. Les versions des paquets et les scripts opérationnels doivent être reconstruits séparément.

Avant toute installation sur un hôte de secours : vérifier les unités avec systemd-analyze verify, les configurations ClamAV avec les outils de la version installée, et tester l'antivirus. Ne pas activer les timers ni les services de notification tant que les identifiants, destinations et réseaux ne sont pas isolés et approuvés. Aucun accès SMTP ou B2 en écriture pendant une répétition. Aucune autorisation PROD.

Tests synthétiques : python3 -m unittest -v test_pra_system_stage. La qualification réelle reste obligatoire. Les répertoires partiels en cas d'erreur d'écriture doivent être supprimés par l'opérateur après inspection; aucun nettoyage global automatique.
