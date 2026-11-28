# Qualification visuelle de la vitrine publique DSIG

## Périmètre
Export statique public uniquement. Ne pas modifier REC, les conteneurs applicatifs, les données, les routes proxy ni la production. Cette procédure ne vaut pas autorisation de publication.

## Préparation reproductible
Depuis un clone Git disposant de Node.js et Python 3 :

```bash
git fetch origin main
ROOT=$(mktemp -d)
git worktree add --detach "$ROOT/source" origin/main
cd "$ROOT/source"
git rev-parse HEAD
node scripts/build-public-site.mjs "$ROOT/public" contact@dsig-consulting.com
node scripts/test-public-site.mjs
node scripts/test-public-indexing.mjs
node scripts/test-legal-compliance.mjs
node scripts/test-public-form.mjs
python -m http.server 8505 --bind 127.0.0.1 --directory "$ROOT/public"
```

Sous Linux utiliser python3 si nécessaire. Arrêter le serveur avec Ctrl+C. Depuis le clone initial, retirer le worktree avec git worktree remove "$ROOT/source" si ROOT est encore défini ; conserver les preuves utiles avant nettoyage. Ne jamais effacer un chemin non vérifié.

## Matrice visuelle
Tester en FR et EN, à 390, 768, 1366 et 1920 px : accueil, menu, annuaire secteurs, fiche transport, fiche logistique, offres, offres SaaS, fiche expertise (URL réelle du sitemap), références, direction, blog, mentions légales et confidentialité. Vérifier liens, contraste, zoom 200 %, focus clavier, absence de débordement horizontal, texte et images, menus et CTA. Capturer les défauts avec URL, largeur, navigateur, SHA et capture. Ne pas qualifier sur une maquette.

## Ressources visuelles
- Logos : consulter REFERENCE_LOGOS_V158.md. Les 13 organisations constituent des expériences professionnelles déclarées, et non des contrats DSIG. Confirmer identité exacte, fichier officiel, conditions d'utilisation et empreinte avant intégration.
- Portraits : obtenir des photos réelles approuvées par chaque dirigeant, autorisation de publication, cadrage et texte alternatif. Maintenir les monogrammes en leur absence.
- Photographies : sélectionner des photos professionnelles dont la licence et la provenance sont documentées. Ne pas présenter une photo illustrative comme un site, une équipe ou un client DSIG.
- Pour chaque ressource, consigner source, titulaire, licence ou autorisation, date de contrôle, fichier final, dimensions, poids et empreinte. Ne pas stocker de données personnelles ou preuves privées dans le dépôt public.

## Décision
Les tests automatisés ne prouvent pas le rendu visuel. Ne pas attribuer un score de maturité ni annoncer la publication sans preuves. Utiliser le contrôle existant scripts/public-release-gate.mjs avec les validations humaines et juridiques requises. Ne pas modifier les garde-fous pour obtenir un PASS.

Statut initial : qualification visuelle non exécutée ; logos officiels et portraits approuvés à collecter ; publication non autorisée par cette procédure.
