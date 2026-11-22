# V150 — Consolidation financière globale

Direction : tableau annuel par devise et détail mensuel, recherche dynamique,
10 lignes par page, export CSV des mois filtrés. La synthèse annuelle reste
complète indépendamment de la recherche. Aucun mouvement ni écriture créés.

Les règlements de prestations et SaaS sont datés de leur encaissement,
les dépenses de leur décaissement et les commissions de leur paiement.
Les allocations SaaS et partenaires sont analytiques : les dépenses sources
ne sont comptées qu'une seule fois. Aucun cumul entre devises.

Une commission et une dépense de même référence (insensible à la casse),
montant, devise et date sont dédupliquées si la dépense est sans mission ou
rattachée à la même opportunité. Sinon les périodes/devises concernées
signalent un conflit et masquent le flux net et les décaissements consolidés.
Les conflits sont recherchés même hors de l'année sélectionnée.

Le rapport exclut les mouvements futurs. Il ne rapproche pas les comptes
bancaires, ne certifie pas l'unicité des encaissements entre systèmes et
ne constitue ni un résultat comptable ni un solde bancaire. Les données
manquantes ou non enregistrées ne sont pas reconstituées.

API GET /api/admin/direction/financial-consolidation : année, page, q,
format json ou csv ; permissions Direction existantes, contrôle d'origine.
Le CSV exporte tous les mois filtrés, sans synthèse annuelle.
