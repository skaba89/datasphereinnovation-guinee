# V213 — Qualification réelle du moteur de sauvegarde local

Le banc utilise server.connect pour construire le schéma applicatif dans un répertoire temporaire, avec DSIG_ENV=DEV, données fictives et clé Fernet éphémère. Il appelle les fonctions existantes operations.encrypted_backup et restore_isolated, sans démarrer le serveur ni utiliser la base active réelle. Tests : aller-retour, SHA256 inchangé, intégrité et clés étrangères, conservation du contenu métier, invalidation des sessions restaurées sans modifier la source, mauvaise clé, archive altérée, refus d'écrasement et de restauration publique.

Ce n'est pas une preuve de sauvegarde PROD opérationnelle, d'export B2, de RPO/RTO réel ou de résistance à un volume important. Le plafond 64 Mio reste inchangé. Aucun secret réel, aucun bucket ni timer créé. Le contrat V212 doit être adapté à la candidate sans bucket distant avant qualification réelle. NO GO maintenu.
