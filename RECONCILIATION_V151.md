# V151 — Régularisations documentées des rapprochements

Le registre Facturation expose les écarts commission/dépense de même référence.
Recherche dynamique, dix lignes par page, historique des propositions et décisions.
L'API Direction permet la consultation selon les droits existants.

- Proposition : compte nominatif COMPTABLE ou ADMIN, justification et référence de pièce obligatoires.
- Validation ou rejet : autre compte nominatif ADMIN, avec motif. Pas de clé de secours ni auto-validation.
- DISTINCTS : deux mouvements réels, conservés tous les deux dans la consolidation.
- DOUBLON : montant et devise identiques obligatoires ; la dépense est le mouvement de référence, la commission est dédupliquée dans sa période.
- Une demande est liée à une photographie exacte des deux mouvements ; tout changement invalide son application. Un rejet permet une nouvelle proposition.

Les sources, soldes de factures et analyses partenaires ne sont pas modifiés.
Le rapport consolidé affiche les écarts approuvés séparément des écarts non résolus.
Les décisions ne sont pas des écritures comptables ni une preuve de rapprochement bancaire.
Les justificatifs sont référencés, pas téléversés. La pièce doit être contrôlée par le valideur.
