# V161 — Mentions légales FR/EN et confidentialité

Statut : **NO-GO publication**. Les pages existent, mais l’identité juridique n’est pas validée ; la porte de publication reste bloquée.

## Ce qui est livré

- `/mentions-legales.html` et `/legal-en.html` (REC et export public), `noindex,nofollow`, hors sitemap.
- Notice de confidentialité publique FR/EN (`/confidentialite.html`, `/privacy-en.html`) décrivant uniquement les traitements réels de la vitrine statique : aucun formulaire, compte, cookie, outil d’audience ou ressource tierce ; contact par lien e-mail ; journaux techniques possibles chez l’hébergeur.
- Notices REC (`dist/confidentialite.html`, `dist/privacy-en.html`) explicitement limitées à l’environnement de recette, distinct du site public.
- Liens « Mentions légales / Legal notice » et « Confidentialité / Privacy » dans les pieds de page (accueil, expertises, blog, secteurs, offres, notices).
- Source unique : `scripts/legal-content.mjs`. Les 96 pages indexables et le sitemap sont inchangés.

## Blocage

- Tout champ juridique vaut `null` tant qu’il n’est pas confirmé. Il s’affiche « Non publié — en attente de validation officielle » / « Not published — awaiting official validation », jamais sous forme de valeur fictive.
- `assertPublishable` refuse : valeur non confirmée, confirmation sans source officielle ni validateur nommé, valeurs de type TODO, XXX, « à confirmer », 0000.
- `scripts/public-release-gate.mjs` ajoute le contrôle `legal_identity` : même avec les 7 approbations humaines, la publication reste `FAIL` tant qu’un champ manque. `node scripts/legal-content.mjs` liste les champs manquants (code de sortie 1).

## Informations juridiques manquantes (17)

| Section | Champ | Pièce attendue |
|---|---|---|
| Éditeur | Dénomination sociale officielle | Statuts / extrait RCCM |
| Éditeur | Forme juridique | Statuts |
| Éditeur | Capital social | Statuts |
| Éditeur | Numéro RCCM | Extrait RCCM |
| Éditeur | NIF | Attestation fiscale |
| Éditeur | Adresse du siège social | Statuts / extrait RCCM |
| Éditeur | Représentant légal | Statuts / PV de nomination |
| Éditeur | Directeur de la publication | Décision du représentant légal |
| Hébergement | Hébergeur (raison sociale) | Contrat ou facture d’hébergement |
| Hébergement | Adresse de l’hébergeur | Mentions officielles de l’hébergeur |
| Hébergement | Contact de l’hébergeur | Mentions officielles de l’hébergeur |
| Confidentialité | Responsable du traitement | Décision du représentant légal |
| Confidentialité | Prestataire de messagerie | Contrat de la boîte `contact@dsig-consulting.com` |
| Confidentialité | Durée de conservation des e-mails | Politique interne validée |
| Confidentialité | Durée de conservation des journaux techniques | Configuration hébergeur / proxy |
| Confidentialité | Cadre juridique applicable | Revue juridique (Guinée et publics visés, dont France) |
| Confidentialité | Autorité de contrôle compétente | Revue juridique |

## Checklist de validation humaine

1. Fournir les pièces officielles ci-dessus ; aucune donnée reprise d’un modèle ou d’un autre site.
2. Revue juridique humaine : exigences applicables en Guinée et pour les publics visés, texte des mentions et de la notice.
3. Renseigner chaque champ dans `scripts/legal-content.mjs` avec `value`, `confirmed: true`, `source` (référence de la pièce) et `validatedBy` (nom du validateur).
4. Régénérer les pages REC : `node scripts/legal-content.mjs --write-dist`.
5. Exécuter `node scripts/test-legal-compliance.mjs` puis la CI complète ; adapter le test (champs `null` attendus) dans la même PR de validation.
6. Nouveau SHA ⇒ nouvelles preuves et approbations dans le registre privé (`legal_privacy_review`, `owner_approval`, etc.). Aucun déploiement automatique.

## Contrôles

`node scripts/test-legal-compliance.mjs` (CI et image publique), `node scripts/test-public-release-gate.mjs`, `node scripts/test-public-site.mjs`, `browser_e2e.PublicExportBrowserTests` (pied de page, `noindex`, responsive 360/768/1280 px).

Aucun changement du VPS, du proxy Caddy partagé, de REC/PROD ni des registres privés d’approbation.
