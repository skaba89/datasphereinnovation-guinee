# V80 — Recette métier de bout en bout

Scénario automatisé `IntakeTests.test_end_to_end_prospect_to_paid_contract` sur serveur HTTP et base SQLite temporaires. Aucun envoi réel, aucune donnée client. Les comptes nominatifs utilisent les clés de recette de la fixture ; la MFA stricte et les sessions restent couvertes séparément par la CI navigateur.

| Acteur | Action | Résultat attendu |
|---|---|---|
| Prospect | Demande de régie | Demande créée |
| Commercial | Qualification et conversion | Une seule opportunité liée, organisation conservée |
| RH | Profil disponible | Consultant créé |
| Commercial | Devis, transmission et acceptation | Devis accepté, mission refusée avant signature |
| Commercial | Enregistrement du contrat signé fictif | Mission éligible |
| Projet | Affectation | Mission créée |
| Consultant | Soumission CRA | Auto-validation refusée |
| Comptable | Facturation avant validation | Refus |
| Projet | Validation CRA | 600 EUR de revenu, 425 EUR de coût |
| Comptable | Facture et règlements 200 + 400 EUR | Solde nul, surpaiement refusé |
| Comptable | Décaissement fictif de 425 EUR | Flux affecté 175 EUR |
| Projet | Clôture | Mission terminée |
| Direction | Pilotage client et mission | Marge validée 175 EUR, créance nulle |

Exécuter `python -m unittest -v test_server.IntakeTests.test_end_to_end_prospect_to_paid_contract` dans un environnement de test. Ce scénario API ne constitue pas une recette navigateur réelle ni une autorisation de production. Rejouer le parcours dans REC restreinte avec des données fictives, et joindre les preuves expurgées au registre V79.
