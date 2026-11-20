# V43 — Recette automatisée isolée sur VPS

Exécuter depuis le dépôt : `bash scripts/acceptance-isolated.sh`. Le script construit une image candidate distincte à partir du commit Git et lance l'ensemble des tests Python dans un conteneur temporaire, sans réseau externe, ports publiés, secrets du VPS ni volume REC/PROD. Les tests utilisent leurs bases temporaires. Prévoir ressources disponibles ; le build peut télécharger les dépendances. L'image candidate est conservée pour traçabilité. Aucun déploiement applicatif.

Cette preuve couvre la suite Python, pas les contrôles navigateur ni les 20 scénarios réels de recette. La CI reste requise. Relever le commit, le nombre de tests, le résultat et les anomalies, puis effectuer les scénarios de RECETTE_METIER_V38.md sur HTTPS avec comptes fictifs. Ne jamais confondre PASS automatisé et validation métier réelle.
