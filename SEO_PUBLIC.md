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

## V116 — Identité et zones d'intervention

Les pages publiques incluent des données JSON-LD Organization, WebSite, WebPage
et, pour les expertises, Service et BreadcrumbList. Conakry, Guinée et France
sont des zones d'intervention, pas des adresses de bureaux. Le générateur reprend
l'adresse e-mail approuvée. Ne pas ajouter LocalBusiness, adresse postale,
coordonnées GPS, horaires, téléphone, avis ou certifications sans confirmation.
Après publication, contrôler les pages avec le validateur Schema.org et le test
des résultats enrichis Google. Créer une fiche Google Business Profile uniquement
si l'activité remplit les conditions d'éligibilité et avec les informations réelles.

## V117 — Blog professionnel bilingue

Le catalogue éditorial `scripts/blog-content.mjs` est séparé de REC. Les quatre
guides initiaux sont disponibles en français et en anglais : Data Engineering,
IA, cybersécurité et transformation digitale. Chaque article possède une URL
stable, un lien vers sa traduction, un lien vers l'expertise associée et un
balisage BlogPosting. Les index du blog et les articles figurent dans le sitemap.

Avant une publication, relire et valider le contenu. Ne pas inventer de références
clients, de signatures individuelles ou de dates de publication. Les articles
existants ne déclarent pas de date tant que la publication réelle n'est pas
confirmée. Pour ajouter un guide, compléter les deux langues et conserver les
slugs des articles déjà publiés ; lancer le test SEO avant livraison.

## V118 — Pages sectorielles

Six secteurs disposent de pages dédiées en français et en anglais : mines,
banques, télécommunications, administrations, éducation, transport et logistique.
Les index `/secteurs.html` et `/sectors.html` sont accessibles depuis les accueils.
Chaque page présente des besoins opérationnels, des indicateurs à suivre et des
liens vers deux expertises DSIG. Les pages sont incluses dans le sitemap, avec
canonical, hreflang et JSON-LD WebPage. Le catalogue est maintenu dans
`scripts/sector-content.mjs`. Aucun témoignage ni résultat client fictif.
L'export contient désormais 84 pages indexables ; REC reste privée et noindex.

## V119 — Performance mobile

L'export assemble les feuilles CSS dans leur ordre initial en un seul fichier
par famille de pages, nommé avec une empreinte SHA-256. Les polices locales
restent en `font-display: swap`. Les scripts publics sont différés, la maquette
SVG principale a des dimensions explicites et une priorité haute, le logo de
pied de page est chargé paresseusement. Aucun changement du bundle REC.

Le test CI impose un seul téléchargement CSS par page, au plus 14 Kio de CSS
et 12 Kio de HTML après gzip, 4 Kio de JavaScript public gzip et 8 Kio pour la
maquette SVG. Ces budgets sont des tailles locales, pas des mesures réseau.
Après publication, activer la compression sur le vhost public uniquement et
mesurer les Core Web Vitals (LCP, INP, CLS) sur mobile avec PageSpeed Insights
et Search Console. Ne pas déclarer de score réel avant la mesure publique.

## V120 — Contrôle de publication et moteurs de recherche

Après publication HTTPS approuvée, depuis un réseau **non autorisé en REC** :

```bash
node scripts/check-public-indexing.mjs
```

Ce contrôle en lecture seule vérifie robots.txt, le sitemap (au moins 84 URL),
chaque réponse HTML et canonical, les directives d'indexation, le refus des
routes privées et la restriction REC. Il ne soumet aucun contenu à un moteur,
ne modifie ni DNS ni proxy et ne prouve pas l'indexation effective. En CI,
`node scripts/test-public-indexing.mjs` utilise uniquement des réponses simulées.

### Comptes propriétaires

1. Dans [Google Search Console](https://search.google.com/search-console/),
   ajouter la propriété Domaine `dsig-consulting.com`. Ajouter uniquement le
   TXT fourni par Google à la zone DNS après validation du propriétaire ; ne
   remplacer aucune entrée existante ni modifier le MX. Voir la [documentation
   de vérification](https://support.google.com/webmasters/answer/9008080).
2. Après contrôle de publication PASS, soumettre
   `https://dsig-consulting.com/sitemap.xml` dans la propriété publique ;
   vérifier l'état du sitemap et inspecter quelques URL FR/EN. Ne pas soumettre
   d'URL REC. Voir le [rapport Sitemaps](https://support.google.com/webmasters/answer/7451001).
3. Dans [Bing Webmaster Tools](https://www.bing.com/webmasters/), importer la
   propriété publique Google vérifiée ou utiliser la vérification manuelle.
   Soumettre le sitemap si nécessaire, puis contrôler sa lecture.
   [Guide Bing](https://www.bing.com/webmasters/help/add-and-verify-site-12184f8b).

### Suivi hebdomadaire (valeurs réelles uniquement)

Conserver hors Git les exports des consoles avec date, moteur, URL et période.
Suivre les pages indexées/exclues, clics, impressions, CTR, position moyenne,
requêtes par langue et pays, erreurs d'exploration et Core Web Vitals.
Comparer des périodes de 28 jours équivalentes. Si une métrique est indisponible,
indiquer « non mesurée » et non zéro. Aucun identifiant, jeton ni secret dans Git.
Google et Bing peuvent découvrir les pages sans garantir leur indexation.

## V121 — Déploiement Docker public autonome

Le Dockerfile public génère les pages dans un étage Node puis copie uniquement
l'export statique dans Caddy. Aucun serveur Python, secret, volume REC ou port
publié sur l'hôte. Le conteneur utilise un utilisateur non root et un système
de fichiers en lecture seule. Le proxy existant termine TLS sur le réseau edge.
Le job CI `public-docker-smoke` vérifie l'image en isolation.

Préparer sur le VPS, seulement après validation CI et approbation des coordonnées
et mentions légales :

```bash
SHA=$(git rev-parse HEAD)
# Remplacer par la boîte commerciale approuvée et vérifiée.
read -r -p 'Adresse commerciale DSIG : ' DSIG_PUBLIC_EMAIL
test -z "$(git status --porcelain --untracked-files=no)"
docker build -f Dockerfile.public --build-arg DSIG_PUBLIC_EMAIL="$DSIG_PUBLIC_EMAIL" --label "org.opencontainers.image.revision=$SHA" -t "dsig-public:$SHA" .
# V122 : fournir le registre privé validé décrit ci-dessous.
bash scripts/deploy-public.sh "$SHA" --activate-public /home/ubuntu/dsig-public-release.json
```

Avant activation, vérifier que le projet `dsig-public` et l'alias réseau
`dsig-public-vitrine` ne sont pas déjà utilisés par une autre application.
L'activation ne modifie pas le proxy. Après vérification de l'existence et de
l'unicité du vhost public, sauvegarder la configuration du proxy, examiner
`deploy/public/edge.caddy.example` et ajouter uniquement le vhost public.
Valider la configuration complète du proxy avant rechargement. Ne pas toucher
aux vhosts REC, MineFleet ou autres. Contrôler ensuite depuis un réseau externe
avec `node scripts/check-public-indexing.mjs`.

Le script tente le retour à l'image précédente si le nouveau service ne devient
pas sain. Pour un retour volontaire, conserver le SHA de la version précédente
et relancer `bash scripts/deploy-public.sh SHA_PRECEDENT --activate-public REGISTRE_PRIVE_PRECEDENT`.
Lors du premier lancement sans image précédente, maintenir le vhost non activé
si le contrôle échoue. Aucun nettoyage Docker global ni suppression de volumes.

## V122 — Autorisation de publication

Avant toute activation, copier le modèle de registre hors du dépôt :

```bash
umask 077
cp -n deploy/public/release-gate.example.json /home/ubuntu/dsig-public-release.json
chmod 600 /home/ubuntu/dsig-public-release.json
node scripts/public-release-gate.mjs "$(git rev-parse HEAD)" /home/ubuntu/dsig-public-release.json
```

Le modèle échoue volontairement tant que les sept contrôles humains ne sont
pas renseignés. Pour chaque contrôle, noter le responsable et une référence
de preuve réelle, sans secret. Le SHA et l'adresse commerciale doivent être
ceux de l'image candidate. Le script d'activation refuse une approbation
manquante, une révision différente ou une adresse incohérente avec l'image.
Le contrôle valide la structure du registre, pas la véracité des preuves.

Informations à confirmer avec le responsable : dénomination juridique exacte,
immatriculation et siège, responsable de publication, hébergeur, coordonnées
commerciales, notice de confidentialité et textes applicables. Ne rien inventer.
Le contrôle `legal_privacy_review` reste PENDING jusqu'à revue du contenu
effectivement publié. Aucun déploiement ni modification du DNS automatique.

## V123 — Supervision publique

Après publication approuvée, exécuter `python3 scripts/monitor-public.py`.
La sonde HTTPS vérifie le nom et la chaîne du certificat, sa durée restante
(au moins 21 jours), quatre routes et leurs marqueurs, ainsi qu'un seuil de
réponse de 5 secondes. Le résultat JSON ne contient aucun secret. Le contrôle
SEO complet reste `node scripts/check-public-indexing.mjs`.

Les unités `dsig-public-monitor.service`, `dsig-public-monitor.timer` et
`dsig-public-alert.service` sont à installer uniquement après le lancement.
Préparer `/etc/dsig-public-alert.env` (root, mode 0600) avec les variables
`DSIG_PUBLIC_ALERT_SMTP_HOST`, `DSIG_PUBLIC_ALERT_FROM`, `DSIG_PUBLIC_ALERT_TO`,
`DSIG_PUBLIC_ALERT_SMTP_USER`, `DSIG_PUBLIC_ALERT_SMTP_PASSWORD` ; SMTP TLS
port 465. Tester l'envoi avec le service d'alerte après accord du destinataire.
Installer ces trois unités, daemon-reload puis enable --now uniquement le
timer public. Le journal indique les résultats ; chaque échec peut déclencher
un mail, y compris les échecs répétés toutes les cinq minutes. Prévoir une
supervision externe indépendante pour détecter une panne totale du VPS.
Pour arrêter le monitoring public : `sudo systemctl disable --now dsig-public-monitor.timer`.
Aucun redémarrage automatique de la vitrine, aucune modification des timers REC.
