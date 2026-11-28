# V175 — Formulaire de contact public (issue #156, étape 2/2)

Le formulaire public est **prêt mais verrouillé**. Il n'apparaît sur la vitrine que si l'image publique est construite avec `DSIG_PUBLIC_FORM=enabled`, **et** cette construction échoue tant qu'une des 17 informations juridiques (V161) n'est pas validée.

## Construction

```bash
# Par défaut (inchangé) : lien e-mail, aucune route API, connect-src 'none'
docker build -f Dockerfile.public --build-arg DSIG_PUBLIC_EMAIL=contact@dsig-consulting.com -t dsig-public:<sha> .

# Formulaire activé (échoue aujourd'hui : "legal information is incomplete (17 missing)")
docker build -f Dockerfile.public --build-arg DSIG_PUBLIC_EMAIL=contact@dsig-consulting.com \
  --build-arg DSIG_PUBLIC_FORM=enabled -t dsig-public:<sha>-form .
```

L'étiquette `com.dsig.public.form` de l'image indique le mode (`disabled` / `enabled`).

## Ce que change le mode `enabled`

| Élément | Désactivé (défaut) | Activé |
|---|---|---|
| Accueil FR/EN | Lien e-mail | Formulaire (nom, organisation, e-mail, téléphone/WhatsApp facultatif, type, message, notice, case, pot de miel) |
| Types proposés | — | Devis, démonstration SaaS, partenariat, conseil et expertise, formation, autre |
| Script | — | `public-contact.js` (même origine, anti-double envoi, messages accessibles, repli e-mail en cas de panne) |
| Notice de confidentialité | « aucun formulaire » | Section « Formulaire de contact » : données, finalité, chiffrement, durée (`email_retention`), responsable (`data_controller`) |
| Caddy interne de l'image | Inchangé | `POST /api/contact` → `dsig-contact:8090` (8 Ko max), `connect-src 'self'`, proxys privés de confiance (IP réelle pour la limitation de débit) |
| Proxy partagé | Inchangé | **Inchangé** |

Source unique du Caddyfile : `deploy/public/Caddyfile`, transformé par `scripts/public-caddyfile.mjs`.

## Ordre de mise en service (avec approbations explicites)

1. Renseigner et valider les 17 champs de `scripts/legal-content.mjs` (pièces officielles, validateur nommé).
2. Déployer le service de contact fermé (`CONTACT_SERVICE_V174.md`) sur le réseau `edge`.
3. Construire la vitrine en mode `enabled` depuis le SHA approuvé, puis la qualifier en isolation.
4. Remplir le registre `public-release-gate` (7 approbations) ; preuve d'un envoi et d'une notification réels.
5. Ouvrir le service : `DSIG_CONTACT_ENABLED=1`. Retour arrière : remettre l'image vitrine `disabled` et/ou `DSIG_CONTACT_ENABLED=0`.

## Vérification

```bash
node scripts/test-public-form.mjs      # refus sans données juridiques, rendu FR/EN, notice, Caddyfile
python -m pytest browser_e2e.py -k public_form_submission   # validation, envoi, double clic, erreurs, panne, CSP, mobile
```
CI : la construction `enabled` doit **échouer** avec le message juridique ; un mode inconnu est refusé ; l'image par défaut porte l'étiquette `disabled`.
