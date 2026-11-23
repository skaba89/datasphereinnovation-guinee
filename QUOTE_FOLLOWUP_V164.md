# V164 — Relance automatique des devis sans décision

Une seule relance polie par **version de devis**, envoyée au prospect quand :

- le devis est au statut `PROPOSE` et sa version actuelle a été **transmise il y a au moins 7 jours** ;
- il est encore valide (date de validité non dépassée) ;
- l'opportunité est toujours ouverte (Prospect → Négociation) ;
- l'opportunité vient d'une demande web (hors candidature spontanée) qui a déjà reçu un accusé de réception.

Un devis accepté, refusé, expiré ou une opportunité perdue ne déclenche aucune relance. Une nouvelle version transmise ouvre droit à une nouvelle relance, 7 jours plus tard.

**Contenu** : message générique FR/EN (langue de la demande), sans montant ni détail du devis, avec la référence de la demande et la possibilité de ne plus être relancé en répondant.

**Fonctionnement** :
- planification lors du rafraîchissement des rappels (`python server.py --refresh-notifications`, déjà planifié par `dsig-rec-notifications.timer`) ;
- envoi par le worker de contact existant (`--send-contact-notifications`), avec les **mêmes règles de destinataires REC** que les accusés : boîte de test, ou adresse explicitement autorisée dans `rec_customer_recipients` ;
- traçabilité : note dans l'historique de suivi de la demande, journal `SYSTEME:relances` (`RELANCE_DEVIS_PLANIFIEE`).

Recette uniquement ; la production reste bloquée.

Tests : `python -m unittest test_quote_followups`.
