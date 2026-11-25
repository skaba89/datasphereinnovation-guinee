# V191 — Précontrôle du bundle et sauvegarde des scripts B2

Le vérificateur compare chaque fichier et son manifeste aux blobs du commit Git explicitement approuvé. Un manifeste et un payload falsifiés ensemble ne suffisent pas à obtenir PASS. Inventaire strict des fichiers, permissions privées, refus des liens symboliques et des composants incomplets. Aucun fichier actif n'est remplacé.

    python3 scripts/rec_release_preflight.py --bundle /private/bundle --repo /private/candidate --commit <sha-complet>

Option après qualification V179 et approbation de la fenêtre : --active-b2-source /home/ubuntu/datasphereinnovation-guinee --rollback-parent /private/rollback (répertoire 0700 préexistant). Les trois scripts B2 sont copiés, avec modes d'origine et SHA256, dans un répertoire privé. Ne pas utiliser pendant une modification concurrente des scripts. Cette sauvegarde ne couvre ni les unités/drop-ins ni les secrets : leur sauvegarde et la répétition du retour arrière restent obligatoires. Aucun renommage de preuve ni suppression de sauvegarde.

PASS signifie seulement intégrité du bundle contre le commit local approuvé. L'identité du dépôt et la confiance dans le commit, la CI, la qualification réelle V179, les journaux, l'approbation de l'exploitant et la disponibilité du rollback doivent être contrôlés séparément. Aucun GO automatique. Le script ne lance aucune commande systemctl ou Docker. Les tests utilisent des dépôts Git synthétiques, aucune donnée réelle. Exécuter python3 -m unittest -v test_rec_release_preflight. Ne pas modifier le VPS avant la qualification du cycle du 26 novembre.
