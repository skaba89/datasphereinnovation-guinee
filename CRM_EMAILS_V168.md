# V168 — Modèles d'e-mails commerciaux

## Utilisation (fiche client)

Section **« Écrire au client »** de `client.html` (rôles avec écriture CRM) :

1. choisir l'opportunité (seules celles avec une adresse e-mail) et le modèle ;
2. **Préparer le message** : aperçu modifiable (objet, texte) avec les champs remplis ;
3. **Enregistrer et ouvrir ma messagerie** : le message est enregistré dans l'historique (section « E-mails préparés » et chronologie de la fiche), puis ouvert dans la messagerie du commercial (`mailto:`).

La plateforme **n'envoie pas** ces e-mails : l'envoi se fait depuis la boîte du commercial, ce qui conserve la conversation dans sa messagerie et évite d'émettre de la prospection depuis un domaine non validé.

## Modèles (`modeles-email.html`, ADMIN)

Six modèles par défaut (présentation, envoi de proposition, relance ; FR et EN). Création, modification, activation/désactivation, verrouillage par version.
Champs autorisés : `{contact}`, `{societe}`, `{opportunite}`, `{commercial}` ; tout autre champ est refusé à l'enregistrement.

## API

- `GET /api/admin/crm/email-templates` — modèles actifs (tous pour ADMIN), `can_compose`, `can_manage`
- `POST /api/admin/crm/email-templates`, `PATCH /api/admin/crm/email-templates/<id>` — ADMIN uniquement
- `POST /api/admin/crm/emails/preview` `{opportunity_id, template_id}` — aperçu, rien n'est enregistré
- `POST /api/admin/crm/emails` `{opportunity_id, template_id, subject, body}` — enregistrement + audit `EMAIL_COMMERCIAL_PREPARE`
- `GET /api/admin/crm/emails?opportunity_id=…` — historique (lecture CRM)

## Vérification

```bash
python -m unittest test_crm_emails
python -m pytest browser_e2e.py -k client_email_templates
```
