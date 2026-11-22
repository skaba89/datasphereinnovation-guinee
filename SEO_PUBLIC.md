# Vitrine publique DSIG — publication indépendante

Le serveur REC et son dossier dist restent privés et non indexables. Le générateur
crée une nouvelle arborescence statique sans pages d'administration ni formulaire
connecté à la base de recette. Ne jamais publier dist directement.

## Préparation

Avec Node.js 22, et après approbation d'une adresse commerciale DSIG réellement
opérationnelle :

```bash
node scripts/test-public-site.mjs
node scripts/build-public-site.mjs /chemin/nouveau-dossier-public contact-approuve@dsig-consulting.com
```

Le générateur refuse un dossier existant. L'adresse ci-dessus est un exemple,
pas une adresse confirmée. Les pages statiques FR/EN comportent les contenus
des expertises, canonical, hreflang, métadonnées et sitemap. Le contact est un
lien e-mail; aucun envoi ni stockage sur le VPS de recette.

## Publication (validation humaine requise)

- Vérifier les mentions légales et la notice de confidentialité avec le responsable,
  et tester la boîte commerciale.
- Publier uniquement le dossier généré sur un hôte HTTPS statique dédié à
  dsig-consulting.com. Ne pas modifier rec.dsig-consulting.com, le réseau edge
  existant ni les autres applications. Interdire les API et les listings de dossiers.
- Vérifier les HTTP 200 publics pour /, /en.html, /robots.txt, /sitemap.xml et les
  expertises; confirmer l'absence de X-Robots-Tag noindex sur les pages du sitemap.
- Vérifier que /accounts.html et /api/admin/requests restent inaccessibles sur
  la vitrine et que REC reste privé.
- Valider le domaine dans Google Search Console, soumettre sitemap.xml et examiner
  la couverture, les pages exclues, Core Web Vitals et requêtes. Aucune garantie
  de positionnement ni d'indexation immédiate.
- Conserver la version statique précédente pour un rollback du seul site public.

Priorités éditoriales : Data Engineering Guinée, cabinet Data et IA Conakry,
transformation digitale, cybersécurité, BI, architecture SI, logistique et SaaS.
Publier des cas réels autorisés et des contenus utiles, sans références,
certifications, coordonnées ou avis inventés. Ajouter ultérieurement un formulaire
public uniquement après validation du traitement des données et de la sécurité.
