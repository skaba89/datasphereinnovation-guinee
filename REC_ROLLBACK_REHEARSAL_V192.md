# V192 — Répétition isolée du déploiement et rollback B2

Le programme vérifie le bundle V190/V191 contre le commit Git attendu et contrôle la cohérence interne du snapshot V191. Il crée exclusivement un nouveau dossier privé de répétition, copie les trois fichiers d'origine et leurs permissions, remplace les fichiers par les versions candidates, vérifie les octets et modes, puis restaure et vérifie les trois fichiers précédents. Aucun script copié n'est exécuté. Aucun appel Docker/systemd/B2, aucun fichier actif modifié.

    python3 scripts/rec_rollback_rehearsal.py --bundle /private/bundle --snapshot /private/snapshot --repo /private/candidate --commit <sha-complet> --scratch-parent /private/rehearsals

Le répertoire parent doit exister en 0700 et être sous contrôle exclusif de l'opérateur. Utiliser des entrées indépendantes et stables, issues de V191; vérifier leur provenance. Le snapshot n'est pas signé et son manifeste ne démontre pas à lui seul l'authenticité de l'ancien état. Le rapport PASS signifie uniquement que la répétition des trois scripts en sandbox est réussie. Les tests injectent une panne après chacune des trois substitutions. Le retour arrière en cas de panne de disque, de coupure électrique ou d'échec de restauration n'est pas garanti; un dossier partiel reste disponible pour inspection. Pas de répétition systemd, pas de validation métier, pas de GO PROD. Les modes Git des candidats deviennent 0644 ou 0755 dans la sandbox, les répertoires restent privés. Ne pas déployer avant qualification du cycle V179 du 26 novembre.

Tests: python3 -m unittest -v test_rec_rollback_rehearsal. La qualification réelle des unités et des drop-ins, des journaux du cycle B2 et des dépendances reste nécessaire.
