# V165 — Facturation automatique (recette)

## Rappels internes (centre de notifications)

Calculés à chaque `python server.py --refresh-notifications` (DEV/REC), sans donnée de contact client :

| Type | Déclencheur | Priorité |
|---|---|---|
| `ECHEANCE_A_FACTURER` | Ligne d'échéancier `PREVU`, non rapprochée, prévue dans les 7 jours ou en retard | URGENT si en retard |
| `JALON_A_FACTURER` | Mission au forfait dont les jalons validés dépassent le montant déjà facturé | A_TRAITER |
| `FACTURE` (existant) | Créance échue non soldée | URGENT |

La clé du rappel de jalon est la date de la dernière validation : un nouveau rappel n'apparaît qu'après une nouvelle validation.

## Relance automatique des factures échues (REC uniquement)

Planifiée par la même commande `--refresh-notifications`, dans la file `contact_mail` existante :

- au plus **deux** e-mails par créance : n°1 à partir de J+7, n°2 à partir de J+21 et au moins 14 jours après le n°1 ;
- seulement si la créance a un solde positif et si la mission provient d'une demande web (hors candidature) ayant reçu l'accusé de réception ; la langue est celle de cet accusé ;
- suspendue si une relance manuelle a été enregistrée dans les 7 derniers jours ;
- le message cite la référence et l'échéance de la créance, **jamais le montant**, et invite à ignorer le rappel si le règlement est déjà fait ;
- règles de destinataires REC identiques aux accusés de réception : boîte de test, ou adresse explicitement listée dans `rec_customer_recipients` ;
- chaque planification est tracée dans l'historique de recouvrement (`billing_reminders`, mention « Relance automatique n°… ») et le journal d'audit (`SYSTEME:recouvrement`, `RELANCE_FACTURE_PLANIFIEE`).

Aucun nouveau service ni minuteur : l'envoi utilise `--send-contact-notifications` déjà planifié en recette. Aucun envoi en production.

## Vérification

```bash
python -m unittest test_billing_automation
```
