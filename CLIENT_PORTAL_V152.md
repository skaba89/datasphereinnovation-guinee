# V152 — Portail client privé

Créer une organisation de type CLIENT, puis un compte nominatif CLIENT avec
son organisation dans Comptes. L'activation passe par le portail de connexion,
le mot de passe et le MFA obligatoire même si la configuration REC le désactive
pour les autres rôles. Seul le cookie de session est accepté par l'API client.

Le rattachement du compte est fixe : désactiver ou archiver le compte en cas
de changement d'organisation. Les contrats et abonnements sont projetés depuis
les opportunités explicitement associées à l'identifiant de cette organisation.
Une liaison d'opportunité déjà contractualisée ne peut pas être réaffectée ni
supprimée ; rattacher un contrat auparavant non lié exige ADMIN. Les dossiers
sans liaison ne sont pas affichés. Aucun rapprochement par nom.

Le portail affiche les références et périodes des prestations et abonnements,
les factures de prestations (montants internes HT) et SaaS (TTC), leurs règlements
et soldes. Aucun coût, marge, note, identité interne, document ou secret exposé.
Pas d'action de paiement ou modification de contrat.

Les demandes d'assistance alimentent le registre client CRM avec un objectif
interne à J+7 (pas un engagement contractuel). Le client voit le statut et son
texte initial, pas les notes de résolution internes. Recherche et pagination
de dix lignes par registre. Le portail reste exclu de l'export public SEO.

Recette : deux organisations distinctes, MFA, contrôle de l'accès croisé,
origine interdite, accès aux modules internes refusé, désactivation, parcours
navigateur. Environnements REC uniquement ; aucun GO PROD.
