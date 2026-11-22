# V103 — Cycle de vie des comptes

Depuis Comptes, un administrateur peut désactiver temporairement, archiver définitivement ou supprimer un compte jamais utilisé. Les droits et l'éligibilité sont contrôlés côté serveur dans une transaction SQLite.

- Suppression : uniquement sans activation, accès audité, invitation, lien consultant ou affectation de demande (y compris historique). Le journal conserve la décision et réserve l'identifiant supprimé pour éviter une ambiguïté d'identité.
- Archivage : conserve le compte et son historique métier ; révoque sessions, mot de passe, MFA, codes de secours et invitation en attente. L'archivage est définitif ; un trigger SQLite empêche même une réactivation via une ancienne image.
- Le propre compte, le dernier ADMIN actif et le dernier ADMIN actif avec mot de passe et MFA sont protégés des actions destructives et du renouvellement.
- L'administrateur doit confirmer chaque opération dans l'interface. Aucun compte existant n'est supprimé ni archivé lors de la mise à niveau.

La migration est additive (`archived_accounts` et trigger). Sauvegarder et tester la restauration avant déploiement. En cas de rollback, ne pas recréer les identifiants supprimés via l'ancienne interface : celle-ci ne vérifie pas cette réservation. Aucun GO PROD implicite.
