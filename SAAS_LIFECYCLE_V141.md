# V141 — Cycle de vie SaaS

Registre CRM interne, décisions réservées à ADMIN, lecture selon le droit CRM.
Un événement versionné, son auteur, son justificatif et sa date effective restent
dans l'historique. Une version périmée est refusée (409).

- Suspension/réactivation à la date du serveur, pendant un contrat actif.
  Ces décisions sont opérationnelles, sans coupure de service, prorata ni changement de facturation.
- Résiliation documentée à une limite valide de période contractuelle, jamais rétroactive.
  La fin exclusive est raccourcie ; la fin précédente est conservée dans l'événement.
  Refus si une préparation couvre une période postérieure ou si un successeur existe.
  Les factures et règlements ne sont ni effacés ni modifiés. Une résiliation
  est définitive dans le registre ; une nouvelle souscription indépendante est nécessaire.
- Le pilotage commercial affiche les résiliations devenues effectives sur les 30
  derniers jours par produit et devise, séparément du non-renouvellement.
  Il s'agit d'un décompte de contrats, pas d'un taux de churn client.

Les litiges, avoirs, proratas, résiliations hors échéancier et coupures effectives
des produits externes restent des procédures distinctes. Aucun envoi externe.

Recette : vérifier les droits, la concurrence de versions, les échéances préparées,
la conservation des pièces, l'historique et la disparition des périodes post-résiliation.
Déploiement REC et sauvegarde préalable requis, aucune autorisation PROD.
