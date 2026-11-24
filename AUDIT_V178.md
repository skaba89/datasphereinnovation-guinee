# V178 — Point d'étape après la mise à niveau REC (mise à jour de `AUDIT_V173.md`)

Date : 2026-11-24. Ce document **ne vaut pas autorisation de production**. Il remplace la section « score » de
`AUDIT_V173.md` ; le reste de V173 (méthode, anomalies A1–A6) reste valable.

## 1. Preuves du jour (sondes HTTP en lecture seule)

| Sonde | Résultat | Lecture |
|---|---|---|
| `GET https://rec.dsig-consulting.com/api/health` | 200 `{"status":"ok"}` | REC en service |
| `GET https://rec.dsig-consulting.com/app.webmanifest` | 200 | PWA (#171) présente en REC → REC à jour |
| `GET https://rec.dsig-consulting.com/api/admin/crm/tasks` sans jeton | 401 | Tâches CRM (#166) déployées et protégées |
| `GET https://dsig-consulting.com/healthz` | 200 | Vitrine PROD en service |
| `GET https://dsig-consulting.com/mentions-legales.html` | 404 | PROD **inchangée** (V161 non publiée, attendu) |
| En-tête `Strict-Transport-Security` PROD | `max-age=86400` | Posé par le Caddy partagé (hors périmètre) |

Mise à niveau REC du 2026-11-23 (sorties opérateur) : `check-rec-upgrade` PASS après #179, activation `--wait`
réussie, image de retour arrière `dsig-rec-rollback:20261123T224639Z` conservée, aperçu des automatisations :
0 relance, 0 rappel, 0 demande éligible à l'anonymisation. Contrôle navigateur en lecture seule : 12 pages × 2
largeurs, aucune erreur JS ni violation CSP, aucun appel `/api/` mis en cache par le service worker.

## 2. Livré depuis V173 (CI verte à chaque fusion)

| PR | Objet | Anomalie V173 |
|---|---|---|
| #175 | CSP stricte de la vitrine (image publique, pas le Caddy partagé) + test navigateur sous CSP | A4 (CSP) |
| #176 | Téléphone, types de demande alignés, avis de confidentialité REC | A5 |
| #177 | Service de contact PROD dédié, fermé par défaut, chiffré, limité | — |
| #178 | Formulaire public **construit seulement si les 17 champs juridiques sont validés** ; route Caddy de l'image | — |
| #179 | Contrôle de montage du scanner compatible Compose 2.40 | Bloquant REC |
| #180 | Recette métier automatisée (`scripts/acceptance-rec.py`, données fictives, effacement final) | — |
| #181, #182 | Service de contact : connexions bornées, budget de 10 s (slowloris), clé jamais suivie en redirection, journaux sans IP, Caddyfiles validés par Caddy en CI | Revue de sécurité interne |

Reste ouvert : **HSTS long** — l'en-tête vient du Caddy partagé ; le doubler dans l'image créerait deux en-têtes
contradictoires. Décision de l'opérateur du proxy partagé (et `preload` est difficilement réversible).

## 3. Score (fondé sur preuves)

| Critère | Poids | V173 | V178 | Justification du changement |
|---|---|---|---|---|
| Couverture fonctionnelle CRM/ERP | 20 | 18 | 19 | Formulaire public et service de contact prêts (non publiés) |
| Tests et CI | 15 | 14 | 14 | Suites étendues ; échecs locaux Windows connus (verts sous Linux) |
| Sécurité applicative | 15 | 11 | 13 | CSP vitrine, service de contact durci ; **pas de revue indépendante** |
| Déploiement REC vérifié | 10 | 2 | 6 | REC à jour (preuves §1) ; recette métier automatisée **non encore exécutée** |
| Exploitation PROD | 10 | 3 | 4 | Retour arrière préparé et prouvé côté REC ; sauvegarde hors site non prouvée |
| Conformité juridique / données | 15 | 5 | 6 | Conservation livrée ; 17 champs et durée non validés |
| Commercialisation | 15 | 2 | 3 | Formulaire prêt mais bloqué ; contact PROD toujours par e-mail |
| **Total** | **100** | **55** | **65** | |

Le plafond restant (≈ 34 points) dépend d'actions **humaines** ; aucune PR ne peut les remplacer.

## 4. Chemin vers 99/100 (ordre recommandé)

| # | Action | Qui | Points visés |
|---|---|---|---|
| 1 | Exécuter `scripts/acceptance-rec.py` sur le VPS, puis contrôles téléphone et compte DIRECTION (MFA) | Opérateur | REC +3 |
| 2 | Fournir les 17 champs juridiques avec pièces (`node scripts/legal-content.mjs`) | Direction | Conformité +5, Commercialisation +2 |
| 3 | Valider la durée de conservation et le transfert Resend (ou un autre prestataire) | Direction | Conformité +4 |
| 4 | Installer le minuteur de conservation et le rapport hebdomadaire en REC | Opérateur | Exploitation +1 |
| 5 | Prouver une sauvegarde hors VPS et une restauration isolée (`export-offsite.py`, `RECETTE_ISOLEE_V43.md`) | Opérateur | Exploitation +4 |
| 6 | Revue de sécurité indépendante (service de contact en priorité, seul composant exposé) | Tiers | Sécurité +2 |
| 7 | Approbations `public-release-gate`, puis publication vitrine V161 + formulaire + service de contact | Direction + opérateur | Commercialisation +10, PROD |
| 8 | Supprimer le dossier privé de mise à niveau REC (`/home/ubuntu/dsig-upgrade-v176.*`) après validation | Opérateur | Hygiène des secrets |

Aucun GO n'est donné par ce document.
