# V128 — Simulation commerciale SaaS

Dans le CRM privé REC, sélectionner une solution du catalogue existant et saisir la devise, la période mensuelle ou annuelle, le nombre d'unités facturables et le prix unitaire par période. Les unités dépendent du modèle commercial à négocier (sites, équipements, utilisateurs, etc.). Saisir le total des options récurrentes pour l'ensemble du scénario, puis les frais ponctuels d'installation et de formation.

Calcul HT : montant récurrent par période = quantité × prix unitaire + options ; ARR estimé = montant récurrent × 12 pour la mensualité, ou montant annuel pour l'annuité ; MRR estimé = ARR / 12 ; première année = ARR + frais ponctuels. Les frais ponctuels ne sont pas inclus dans le MRR ou l'ARR. Les montants utilisent Decimal et l'arrondi à la précision de chaque devise. Aucun taux de change, aucune TVA ni remise implicite.

Le scénario est calculé côté serveur avec les autorisations CRM d'écriture et n'est pas enregistré. Les résultats ne sont ni un revenu acquis, ni une facture, ni un devis contractuel. Aucun tarif officiel n'est prédéfini. Les produits et les conditions de disponibilité restent ceux du catalogue interne. Aucun abonnement, paiement, renouvellement ou message automatique. Aucun GO PROD.

Exemple fictif : 10 unités à 25,50 EUR/mois, options 10 EUR/mois, installation 200 EUR et formation 100 EUR. MRR 265 EUR, ARR 3180 EUR, première année 3480 EUR. Répéter avec une période annuelle et vérifier que le MRR est 22,08 EUR et le premier total annuel 565 EUR. Les tests couvrent également les montants invalides, les permissions et l'absence de mutation métier.
