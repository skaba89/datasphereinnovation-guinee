# V169 — Devis en PDF

Module **Devis** : boutons **« Télécharger le PDF »** (français) et **« PDF anglais »** dans les actions de chaque devis.
Le fichier `DSIG-<année>-<identifiant>-v<version>.pdf` est prêt à joindre à l'e-mail de proposition (V168).

## Contenu

- Bandeau DSIG, référence, date, validité, client et contact ; objet ; périmètre ; tableau de prix (régie : jours × tarif journalier ; forfait : montant) ; total HT ; conditions commerciales ; pagination automatique.
- **Jamais** de coût journalier interne, de frais internes ni de marge.
- Filigrane et pied de page « Recette — document non contractuel » : les mentions légales de l'émetteur (dénomination, RCCM, NIF, adresse) ne sont pas encore validées (voir `LEGAL_COMPLIANCE_V161.md`) ; aucune n'est imprimée.

## Technique

- `quote_pdf.py` : PDF 1.4 généré en Python standard (polices Helvetica intégrées au lecteur, encodage WinAnsi, flux compressés), sans nouvelle dépendance.
- `GET /api/admin/quotes/<id>/pdf?lang=fr|en` — permission `quotes` en lecture ; réponse `application/pdf`, `Cache-Control: no-store` ; audit `DEVIS_PDF`.
- L'aperçu imprimable existant reste disponible ; l'ancien export texte est remplacé par le PDF.

## Vérification

```bash
python -m unittest test_quote_pdf
python -m pytest browser_e2e.py -k prospect_to_paid
```
