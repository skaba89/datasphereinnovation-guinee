# V140 — Pilotage commercial SaaS

CRM et Direction : tableaux par produit et devise, recherche et pagination
de dix lignes. Actualisation à la connexion ou sur demande.

- Pipeline : offres comptées dans leur dernier état, offres ouvertes hors
  validité isolées. Conversion des offres = acceptées / (acceptées + refusées).
- Conversion des opportunités = opportunités distinctes avec abonnement
  enregistré / opportunités distinctes avec offre, dans chaque groupe.
  Ce n'est pas un décompte des personnes morales ni un taux de cohortes CRM.
- MRR et ARR HT : abonnements actifs à la date de consultation.
- Prévision HT à J+90 inclus : échéances contractuelles non facturées,
  hors échéanciers non alignés (signalés), sans hypothèse commerciale.
  Échéances passées non facturées isolées. Ne pas ajouter au CA déjà facturé
  sans contrôler le périmètre.
- Renouvellements : expirations dans les trente derniers jours, lien de
  succession enregistré ou absent. Proxy de non-renouvellement : contrats
  actifs à J-30, échus sans successeur lié / contrats actifs à J-30.
  Ce n'est ni un churn client ni une résiliation anticipée mesurée.

Les taux sans dénominateur sont non applicables. Aucun cumul interdevises.
Les routes de lecture respectent les droits CRM et Direction indépendamment.
Les agrégats ne contiennent aucun contact ni référence de facture.
