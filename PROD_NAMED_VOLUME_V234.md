# V234-E1 — Administrateurs nominatifs sur volume isolé

Le module réutilise le bootstrap transactionnel V207 sur une base métier existante, sous verrou consultatif V234-D2. Il ouvre la base en mode rw sans création implicite. Les clés d'activation sont retournées exclusivement à l'appelant de confiance, jamais imprimées. La lecture de readiness ne révèle aucune identité et ne confère aucune autorisation.

Le volume doit être isolé, sa provenance contrôlée et tous les écrivains arrêtés. La présence des enregistrements MFA n'est pas une preuve de connexion effective. L'activation nominative, la vérification TOTP réelle, la distribution sécurisée des clés et le contrôle de démarrage runtime restent à intégrer. Aucun serveur ne démarre, aucun compte réel n'est créé par cette PR.

Tests : `python -m unittest test_prod_private_named_volume test_prod_named_bootstrap` sous Linux non-root. Rollback : revert du code, conserver les données et les preuves; ne pas réinitialiser les comptes.
