# V158 — Logos des références professionnelles

Les 13 références restent des expériences professionnelles, pas des contrats DSIG ni des partenariats. Conserver la mention existante.

Intégration sur les deux pages du site public, avec grille responsive et logo PNG local, image décorative (nom adjacent), chargement différé, sans appel à un tiers.

## Ajouter un logo authentique

Après vérification de l’identité exacte et des conditions d’utilisation, placer le PNG officiel ou sa conversion fidèle dans `dist/reference-logos/<id>.png` (150 Kio maximum, dimensions maximales 1600 × 1600). Ajouter une entrée au tableau `dist/reference-logos.json` :

```json
{"id":"keyrus","sourceUrl":"https://adresse-officielle-du-fichier","sha256":"empreinte SHA-256 du PNG local"}
```

Calculer l’empreinte avec `sha256sum dist/reference-logos/keyrus.png`. Ne pas ajouter d’illustration générique ni d’URL non validée. Les identifiants autorisés sont listés dans `scripts/reference-logos.mjs`. Pour Arcade, Amayas, MSO-Soft et toute autre identité ambiguë, confirmer l’organisation exacte avant publication.

Le manifeste initial est vide : aucun fichier officiel n’a pu être récupéré et contrôlé. Le nom de chaque référence reste visible. Le test utilise uniquement un PNG synthétique temporaire, jamais publié.

Valider avec `node scripts/test-public-site.mjs`, puis suivre la procédure de publication publique approuvée. Aucun changement du VPS ou de REC.
