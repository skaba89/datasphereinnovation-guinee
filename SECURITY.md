# Sécurité et recette

Cette application est destinée à la recette locale avec des données fictives. La production est volontairement bloquée. Ne pas exposer le serveur HTTP Python à Internet. Générer une clé privée pour chaque environnement et exclure fichiers de données, sauvegardes et secrets du dépôt. Ne pas réutiliser les clés de recette en production.

V15 : session navigateur partagée par cookie HttpOnly, SameSite=Strict, 30 minutes ; contrôle d'origine pour les mutations par cookie. MFA TOTP facultative avec prévention du rejeu et révocation des sessions à l'activation. La rotation administrative de la clé réinitialise également la MFA. Les secrets TOTP restent en clair dans SQLite de recette ; aucune donnée réelle ne doit y être stockée. Le cookie local HTTP n'est pas Secure : TLS et cookie Secure sont indispensables avant production.

V16 : révocation des autres sessions limitée au compte courant, confirmation par mot de passe, journalisation des déconnexions et révocations, contrôle cross-site supplémentaire. Aucun identifiant de session n'est exposé par le compteur.

V17 : nouveaux secrets TOTP chiffrés par Fernet avec une clé externe DSIG_MFA_KEY. Les secrets historiques sont migrés après vérification réussie ; ils restent en clair jusqu'à cette migration, y compris les anciennes sauvegardes. Huit codes de secours aléatoires à usage unique, stockés sous forme de hachage SHA-256, sont fournis à l'activation. Leur utilisation révoque les anciennes sessions. Rotation administrative : suppression des codes et du secret MFA. La clé doit être sauvegardée séparément, sans dépôt Git.

V18 : MFA obligatoire pour ADMIN et, par défaut, DIRECTION, CONTROLE, COMPTABLE, AUDITEUR. Les comptes concernés sans MFA peuvent s'inscrire depuis le portail de connexion mais ne disposent d'aucune permission métier. Les clés initiales ne contournent pas ce contrôle. Matrice vérifiée pour neuf rôles et onze ressources, avec refus des ressources inconnues. La clé bootstrap locale reste une exception d'urgence ; ne pas utiliser en production.

V19 : recette navigateur automatisée avec base et serveur isolés, inscription MFA administrateur, code de secours, session partagée, consultation des onze modules selon le rôle, demande publique et refus d'accès consultant aux comptes. Mes CRA est exclu du menu administrateur conformément à la restriction métier.

V20 : sauvegarde SQLite chiffrée avec clé indépendante, vérification d'intégrité, restauration isolée sans écrasement et révocation des sessions restaurées. Readiness HTTP sans données sensibles. Voir OPERATIONS.md : la sauvegarde distante, planification, alertes et rétention automatisées restent à mettre en place.

Points ouverts : extension de la recette navigateur à toutes les écritures métier, régénération autonome des codes de secours, migration proactive de tous les secrets historiques, rotation des clés de chiffrement, audit de sécurité indépendant, gestion de secrets de production, TLS, séparation par champ, journal d'audit métier fiable et exercices de reprise en conditions représentatives. Aucun déploiement sur GitHub Pages ni conteneur externe via CI.
