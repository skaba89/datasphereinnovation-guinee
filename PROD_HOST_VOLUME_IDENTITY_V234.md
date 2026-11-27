# V234-F7 — Identités hôte et volume

Mesure locale de machine-id (fichier root non modifiable par groupe/autres), empreinte séparée par domaine, inspection du volume Docker local et de son seul consommateur arrêté. Le chemin du volume et ses métadonnées filesystem sont comparés lors de deux observations. Aucun identifiant machine brut ni contenu métier n'est retourné.

Cette mesure nécessite un opérateur autorisé à lire les métadonnées du volume Docker sur l'hôte Linux. Le machine-id peut être cloné et les inodes réutilisés : ces empreintes ne constituent ni une attestation matérielle ni une protection contre un root malveillant. La provenance indépendante, l'exclusivité effective pendant le lancement et la politique du conteneur exécutable restent nécessaires. Le validateur de source existant est réutilisé pour ses contrôles structurels, après vérification explicite que le consommateur est arrêté.

Tests : `python -m unittest test_prod_private_host_volume_identity`. Observations simulées, qualification VPS réelle requise. Rollback : revert du code uniquement, ne pas modifier le machine-id, les volumes ou les services.
