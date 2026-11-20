# Sécurité et recette

Cette application est destinée à la recette locale avec des données fictives. La production est volontairement bloquée. Ne pas exposer le serveur HTTP Python à Internet. Générer une clé privée pour chaque environnement et exclure fichiers de données, sauvegardes et secrets du dépôt. Ne pas réutiliser les clés de recette en production.

V15 : session navigateur partagée par cookie HttpOnly, SameSite=Strict, 30 minutes ; contrôle d'origine pour les mutations par cookie. MFA TOTP facultative avec prévention du rejeu et révocation des sessions à l'activation. La rotation administrative de la clé réinitialise également la MFA. Les secrets TOTP restent en clair dans SQLite de recette ; aucune donnée réelle ne doit y être stockée. Le cookie local HTTP n'est pas Secure : TLS et cookie Secure sont indispensables avant production.

Points ouverts : MFA obligatoire selon le rôle, récupération sécurisée, chiffrement des secrets TOTP, audit de sécurité indépendant, gestion de secrets de production, TLS, séparation par champ, journal d'audit métier fiable, tests end-to-end navigateur et restauration en environnement isolé. Aucun déploiement sur GitHub Pages ni conteneur externe via CI.
