# V195 — Contrôle hors ligne de la configuration PROD

Le module prod_config.py ne démarre aucun serveur et n'autorise jamais PROD. Le verrou V194 reste intact. Le contrôle lit un JSON privé sur stdin avec trois objets prod, rec, candidate, représentant les environnements effectifs (pas des noms de variables Compose). Ne jamais enregistrer ce JSON dans Git, dans les logs ou le partager. Utiliser uniquement une source privée vérifiée par l'opérateur. Le rapport ne contient que les noms des contrôles et leur résultat.

Les origines attendues sont app.dsig-consulting.com (proposition initiale), rec.dsig-consulting.com et candidate.invalid. Les secrets de référence doivent être valides et distincts entre REC et candidate. Le contrôle compare les secrets PROD à ces deux ensembles et vérifie le format des clés Fernet, le token, le chemin SQLite, le chemin ClamAV et la politique MFA. Il ne prouve pas l'entropie, la provenance effective des paramètres, l'existence des sockets, le chiffrement du disque ni l'absence de réutilisation dans d'autres applications. Le domaine client séparé nécessite une évolution ultérieure du contrôle d'origine et des sessions.

Commande de qualification hors ligne : python3 prod_config.py < fichier-prive.json (environnement Python avec requirements.txt). Ne pas créer de secrets réels avant revue de la procédure de bootstrap et de stockage. PASS signifie uniquement conformité des paramètres fournis, jamais GO PROD.

Suite : autorisation signée liée à une release et à une configuration, vérification de provenance, architecture Compose dédiée puis qualification isolée. Aucun changement REC, DNS ou proxy.
