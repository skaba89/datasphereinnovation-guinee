# Sécurité et recette

Cette application est destinée à la recette locale avec des données fictives. La production est volontairement bloquée. Ne pas exposer le serveur HTTP Python à Internet. Générer une clé privée pour chaque environnement et exclure fichiers de données, sauvegardes et secrets du dépôt. Ne pas réutiliser les clés de recette en production.

Points ouverts : MFA, session unifiée, audit de sécurité indépendant, gestion de secrets de production, TLS, séparation par champ, journal d'audit métier fiable, tests end-to-end navigateur et restauration en environnement isolé. Aucun déploiement sur GitHub Pages ni conteneur externe via CI.
