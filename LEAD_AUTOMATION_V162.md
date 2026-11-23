# V162 — Prospect CRM automatique depuis le formulaire

Chaque demande commerciale reçue par `/api/requests` est synchronisée avec le CRM dans la même transaction (échec ⇒ demande non enregistrée, réponse 503).

- **Prospect créé** : opportunité `PROSPECT` (société, contact, e-mail, besoin, mode), relance à J+2, prochaine action « Qualifier la demande web sous 48 h », historique `opportunity_events`.
- **Sans doublon** : si une opportunité ouverte (Prospect → Négociation) porte déjà le même e-mail, la demande y est rattachée (`DUPLICATE`), sans nouvelle opportunité.
- **Attribution** : la demande est affectée au compte COMMERCIAL actif le moins chargé (demandes ouvertes), échéance J+2 ; priorité HAUTE pour une démonstration. Sans commercial actif : non affectée.
- **Qualification humaine conservée** : « Qualifier le prospect CRM » (demande au statut Qualifiée) promeut le prospect en `QUALIFIE` et le rattache à l'organisation, au lieu de créer une seconde opportunité.
- **Candidatures spontanées** : jamais envoyées au CRM.
- **Traçabilité** : table `request_leads`, journal `SYSTEME:site-web` (`PROSPECT_AUTO_CREATED` / `PROSPECT_AUTO_DUPLICATE`), note dans l'historique de suivi.

Recette uniquement. Le formulaire du site public reste désactivé tant que la validation juridique (V161) et la mise en production ne sont pas approuvées.

Tests : `python -m unittest test_lead_automation`, `test_server`, `browser_e2e.BrowserTests.test_browser_prospect_to_paid_contract`.
