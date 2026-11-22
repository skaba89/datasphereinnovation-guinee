# V156 — Qualification transversale DSIG

Le registre passe au schéma 2 : 25 contrôles au lieu de 18. Les anciens registres, même complets, sont refusés. Les 10 gates de production restent obligatoires. Le rapport consolidé indique la liste des contrôles bloquants, sans afficher les références privées. Aucun score de maturité, aucune autorisation de production ni certification réglementaire ne sont déduits de déclarations.

## Recette supplémentaire obligatoire

| Contrôle | Scénario sur REC du SHA exact |
|---|---|
| public_site_seo_isolation | Sitemap, indexabilité des pages publiques, canonical, FR/EN mobile ; accès aux pages privées et fichiers sensibles refusé sur l'image publique |
| saas_subscription_billing_renewal | Offre, abonnement, échéancier, facture, règlement, renouvellement et résiliation sur données fictives ; absence de double comptage |
| partner_commissions_targets | Partenaire, objectifs, commissions, coûts et rapprochement avec la trésorerie par devise |
| client_portal_isolation | Deux organisations fictives, MFA, documents et tickets ; impossibilité d'accéder aux objets de l'autre organisation |
| commercial_automation | Rappels, agrégation, absence de doublons, solde et résolution ; exécution réelle du timer REC et preuve d'erreur sans envoi externe |
| strategic_dashboard | Totaux cohérents avec modules source, taux avec dénominateur nul, devises séparées, rapprochements en attente visibles |
| audit_governance | Pagination stable malgré écritures concurrentes, filtres, refus d'accès et couverture MFA ; examen de la conservation et de l'intégrité du journal |

## Étapes opérateur

1. Fusion après CI verte ; relever le SHA de main. La CI de la PR n'atteste pas le SHA de fusion.
2. Préparer une mise à niveau REC isolée et réversible conformément à REC_UPGRADE_V96.md ; sauvegarde vérifiée, restauration candidate/rollback puis activation approuvée.
3. Vérifier la REC exacte et générer un registre neuf selon QUALIFICATION_V95.md. Exécuter les 25 scénarios et compléter les 10 gates avec preuves réelles.
4. Examiner les blocages du rapport. Même REVIEW_REQUIRED ne signifie que complétude déclarative ; une revue indépendante et une décision explicite restent requises.

## Risques résiduels avant PROD

- Sauvegarde locale seule insuffisante : copie chiffrée hors VPS, clés séparées et test de restauration depuis cette copie.
- Contrôle réseau/TLS depuis les deux origines, supervision externe avec réception constatée, charge et absence d'impact sur les autres services.
- Audit indépendant, politique de rétention, intégrité du journal et gestion des secrets, validation métier et obligations juridiques/fiscales par responsables compétents.
- Une version dédiée PROD reste nécessaire ; le verrou actuel n'est pas levé par V156. Aucun changement sur le VPS.
