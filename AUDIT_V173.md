# V173 — Audit de reprise (phase 0) et état réel du projet

Date : 2026-11-23. Base : `main` = `f85f4e41fdd7bd4b4741536bdb8086ff3182d3b5` (CI verte, 5 jobs).
Méthode : lecture du dépôt, des 30 dernières PR, de l'historique GitHub Actions, des issues #152 et #156, et sondes HTTP **anonymes** (codes de statut uniquement) sur la vitrine et la REC. Aucun accès VPS : tout ce qui relève du serveur est « À confirmer » sauf preuve publique.

## 1. Preuves de déploiement (sondes HTTP du 2026-11-23)

| URL | Code | Conclusion |
|---|---|---|
| `https://dsig-consulting.com/` | 200 | Vitrine PROD en ligne |
| `https://dsig-consulting.com/mentions-legales.html` | 404 | **V161 non déployée en PROD** (cohérent avec #152 : PROD figée sur `e9cfe4a`) |
| `https://dsig-consulting.com/api/requests` | 404 | Aucune API publique (attendu) |
| `https://rec.dsig-consulting.com/api/health` | 200 | REC en ligne |
| `https://rec.dsig-consulting.com/crm.html` | 200 | Ancienne version REC active |
| `…/mentions-legales.html`, `crm-board.js`, `dashboard.js`, `client.html`, `taches.html`, `app.webmanifest` | 404 | **Aucune livraison #153 → #173 n'est déployée en REC** |

En-têtes vitrine : HSTS `max-age=86400` (1 jour), `X-Frame-Options: DENY` ; **pas de Content-Security-Policy** sur la vitrine (le Caddyfile de l'image publique n'en définit pas).

## 2. Tableau de l'existant

Légende : ✅ Vérifié · ◐ Partiel · ✗ Manquant · ? À confirmer.

| Module | Fonctionnalité | Développée | Testée | REC | PROD | Anomalies | Reste à faire |
|---|---|---|---|---|---|---|---|
| Vitrine | 96 pages SEO FR/EN, sitemap | ✅ | ✅ (node + docker) | — | ✅ (version `e9cfe4a`) | Pas de CSP ; HSTS 1 j | CSP + HSTS long dans l'image publique |
| Juridique V161 | Mentions légales / confidentialité, blocage | ✅ | ✅ | ✗ | ✗ | — | **17 champs juridiques** à fournir (humain) |
| Formulaire public V162 | Formulaire vitrine → CRM | ✗ (lien mailto) | — | — | ✗ | — | API publique dédiée, décision d'hébergement, champs téléphone/types |
| Formulaire REC | Saisie, anti-spam (honeypot, rate limit), consentement | ✅ | ✅ | ✅ (ancienne version) | — | Pas de champ téléphone ; types ≠ #156 | Aligner sur #156 |
| Données | Conservation / effacement des demandes | ✅ (#173) | ✅ | ✗ | — | — | Durée à valider ; minuteur à installer |
| CRM | Prospect automatique, doublons, attribution | ✅ (#158) | ✅ | ✗ | — | — | Recette réelle |
| CRM | Kanban, fiche 360°, recherche globale | ✅ (#157, #160, #161) | ✅ | ✗ | — | — | Recette réelle |
| CRM | Tâches, modèles d'e-mails | ✅ (#166, #167) | ✅ | ✗ | — | Transaction ouverte sur base neuve (corrigée #173) | Recette réelle |
| Ventes | Devis PDF FR/EN | ✅ (#168) | ✅ | ✗ | — | — | Identité légale (filigrane non contractuel) |
| Automatisation | Relances devis / factures, rappels « à facturer » | ✅ (#163, #164) | ✅ | ✗ | — | — | Mesurer la file au 1er passage (`--automation-preview`) |
| Pilotage | Cockpit, rapport hebdo e-mail / en ligne / CSV / PDF | ✅ (#159, #162, #165) | ✅ | ✗ | — | — | Fichier `/etc/dsig-rec-report.json`, minuteur |
| Mobile | Shell téléphone, PWA installable, hors connexion sans données | ✅ (#171) | ✅ | ✗ | — | PR WIP #170 fusionnée (sans effet, englobée par #171) | Test sur vrai téléphone en HTTPS |
| Sécurité | Rôles, MFA, CSP stricte (app), audit, origines | ✅ | ✅ | ? | — | — | Revue de sécurité indépendante |
| Exploitation | Sauvegarde chiffrée, restauration isolée, monitoring | ✅ (scripts) | ◐ (tests unitaires) | ? | — | — | Preuves terrain, copie hors VPS |
| CI/CD | 5 jobs, images Docker isolées | ✅ | ✅ (40 dernières exécutions : 39 succès, 1 échec corrigé) | — | — | `Dockerfile.public` : `\n` littéral (corrigé #172) | — |

## 3. Anomalies identifiées pendant l'audit

| # | Anomalie | Gravité | Statut |
|---|---|---|---|
| A1 | `Dockerfile.public` : `\n` littéral dans `RUN` (argument parasite, lisibilité) | Faible | **Corrigée** (#172) + contrôle de non-régression |
| A2 | `connect()` laissait une transaction ouverte sur base neuve (insertion des modèles d'e-mails) → `--refresh-notifications` et `--automation-preview` échouaient | **Élevée** (aurait cassé la planification au premier passage après mise à niveau REC) | **Corrigée** (#173) + test de non-régression |
| A3 | Aucune politique de conservation / suppression des demandes | Élevée (bloquante pour données réelles) | **Corrigée** (#173), durée à valider |
| A4 | Vitrine sans CSP, HSTS court | Moyenne | Ouverte (image publique, hors Caddy partagé) |
| A5 | Formulaire REC sans champ téléphone ; types de demande différents de #156 | Faible | Ouverte |
| A6 | PR #170 (WIP) fusionnée | Nulle (fichiers non branchés, englobés par #171) | Constat |

## 4. Score de maturité (recalculé, fondé sur preuves)

| Critère | Poids | Note | Justification |
|---|---|---|---|
| Couverture fonctionnelle CRM/ERP (code) | 20 | 18 | Cycle prospect → facture complet et testé ; formulaire public absent |
| Tests et CI | 15 | 14 | 159 tests Python, 34 navigateur, 4 suites Node, images Docker ; échecs locaux Windows connus |
| Sécurité applicative | 15 | 11 | Rôles, MFA, CSP, audit, verrous ; **pas de revue indépendante**, vitrine sans CSP |
| Déploiement REC vérifié | 10 | 2 | REC sur une version antérieure à #153 (preuve HTTP) |
| Exploitation PROD (sauvegarde hors site, supervision, rollback prouvés) | 10 | 3 | Procédures écrites, preuves terrain absentes |
| Conformité juridique / données | 15 | 5 | Blocage V161 et conservation (#173) ; 17 champs et durées non validés |
| Commercialisation (formulaire public, contact réel) | 15 | 2 | Contact par mailto uniquement ; V162 non commencée côté public |
| **Total** | **100** | **55** | |

**55/100.** Le code est mûr ; la maturité est plafonnée par l'absence de déploiement REC des livraisons récentes, de preuves d'exploitation et des validations juridiques. Atteindre 99/100 exige des actions **humaines** (pièces juridiques, déploiement REC, revue de sécurité, approbations) qu'aucune PR ne peut remplacer.

## 5. Points nécessitant une validation humaine

1. Les **17 champs juridiques** de V161 (`node scripts/legal-content.mjs` les liste) — pièces : statuts, RCCM, NIF, contrat d'hébergement, etc.
2. **Durée de conservation des demandes** (proposition : 3 ans d'inactivité, `RETENTION_V172.md`).
3. **Base légale et information** du futur formulaire public (intérêt légitime / mesures précontractuelles ; consentement seulement si requis) ; mention du champ téléphone/WhatsApp.
4. **Transfert hors de Guinée** : prestataire d'e-mails Resend (États-Unis) — à valider ou remplacer.
5. **Architecture du formulaire public** : la vitrine est statique derrière le Caddy partagé (interdit de modification). Options : (a) route `/api/contact` ajoutée par l'opérateur du Caddy partagé vers un service PROD dédié ; (b) sous-domaine dédié (ex. `contact.dsig-consulting.com`) ; (c) service tiers de formulaire. **Décision humaine requise** avant tout développement de l'API publique.
6. Approbations de mise en service (registre `public-release-gate`) et revue de sécurité indépendante.

## 6. Prochaine action prioritaire

- **Humain** : déployer `f85f4e4` (ou plus récent) en REC avec `REC_ROLLOUT_V170.md`, puis fournir les pièces juridiques.
- **Technique (sans validation préalable)** : CSP et HSTS de la vitrine dans l'image publique (A4) ; alignement des champs du formulaire REC sur #156 (A5).
