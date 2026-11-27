# V234-D — Classification du volume privé

`prod_private_data_lifecycle.inspect` distingue un répertoire vide d'une base SQLite existante dont les tables requises et l'intégrité sont vérifiées. Il refuse les permissions non conformes, les liens, les fichiers annexes et les bases corrompues. Il ne crée ni ne modifie les données.

L'appelant doit garantir l'exclusivité réelle du volume et l'arrêt de tous les écrivains avant la lecture SQLite immutable. La comparaison des métadonnées ne remplace pas un verrou. Le résultat EXISTING_SCHEMA ne prouve pas la provenance PROD ni la validité complète du schéma. Un journal résiduel exige une récupération contrôlée, jamais une suppression automatique.

Tests : `python -m unittest test_prod_private_data_lifecycle` sous un utilisateur non-root. Rollback : revert de cette PR, aucun changement de volume. L'initialisation transactionnelle, la preuve d'identité du volume, le verrou de cycle de vie, les migrations et le redémarrage autorisé restent à intégrer. Les verrous serveur et Compose restent inchangés.
