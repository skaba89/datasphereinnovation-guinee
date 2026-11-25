# V183 — Préparation Caddy REC hors réseau

Prérequis : kit V3 qualifié par V180 à partir d'une empreinte indépendante, extrait dans un répertoire privé (0600/0700), image Caddy officielle de confiance déjà disponible sur un hôte de secours Linux. Aucun accès au proxy actif, aucun montage hôte, aucun port publié, aucune émission de certificat. Utiliser le véritable nom REC approuvé et l'identifiant sha256 de l'image Caddy locale vérifiée. Ne pas exécuter sur le VPS partagé.

    mkdir -m 700 ~/pra-caddy-stage
    python3 scripts/pra_caddy_stage.py --source /private/v3 --private-stage-parent ~/pra-caddy-stage --hostname rec-dsig.example.org --caddy-image sha256:<id>

Le nom ci-dessus est un exemple, pas une adresse de déploiement. Le script contrôle les deux fichiers listés dans SHA256SUMS et adapte le fragment dans un conteneur éphémère sans réseau. Il refuse les configurations hors du sous-ensemble prévu; notamment imports, substitutions, TLS explicite et upstreams autres que dsig-rec-dsig-1:8080. Une configuration légitime plus complexe peut nécessiter une revue et une évolution du vérificateur. Le contrôle n'est pas une analyse exhaustive des directives, des secrets ou de la sémantique Caddy. Le JSON adapté n'est pas installé. Les entrées extraites doivent rester sous contrôle exclusif de l'opérateur. Le rapport contient uniquement les métadonnées du staging.

Étape ultérieure, distincte et soumise à approbation : provisionner un proxy indépendant, valider les modules et la configuration complète avec caddy validate, vérifier accès, en-têtes et routage sur un domaine de test, préparer les droits DNS et la réémission TLS par ACME. Ne jamais modifier le DNS REC actif, copier les clés privées TLS partagées ni recharger le proxy existant pendant une répétition. La disponibilité HTTPS et la réémission TLS ne sont pas démontrées par caddy adapt.

Tests synthétiques : python3 -m unittest -v test_pra_caddy_stage. L'adaptation Docker réelle et la qualification du véritable kit V3 restent obligatoires. Aucun changement PROD ni cycle B2.
