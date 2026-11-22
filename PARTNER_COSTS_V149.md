# V149 — Charges mutualisées partenaires

La comptabilité affecte une fraction d'un décaissement existant hors mission à un partenaire, avec justificatif. La devise est héritée ; le solde disponible est commun aux affectations SaaS et partenaires. La transaction SQLite verrouille la lecture du solde et l'écriture ; aucune création de décaissement. Les références de commissions identifiées sont exclues et les affectations sont immuables et auditées.

Direction déduit ces coûts de la contribution documentée V147. Le solde des décaissements hors missions non affectés tient compte des deux types d'affectations. Les rapports SaaS et partenaires restent des axes analytiques distincts : ne pas additionner leurs revenus. Les charges restantes et les doublons sous références distinctes ne sont pas automatiquement réconciliés ; aucun bénéfice comptable certifié. Recherche et pagination dix lignes ; ADMIN/COMPTABLE en écriture.
