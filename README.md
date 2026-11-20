# DSIG — recette locale

Version de travail non publiée. Python 3.10+ suffit ; aucune dépendance à installer.

## V14 — Intégration Git et CI

La CI exécute les tests Python 3.10 et 3.12, vérifie la syntaxe JavaScript et construit une image Docker de recette avec smoke test local. Aucun déploiement public et aucune publication d'image. Les fichiers de données, sauvegardes et secrets doivent rester hors Git. Voir `SECURITY.md` pour les limites de la recette.

## V13 — Connexion et conteneurisation

Créer un compte dans `/accounts.html`, puis activer son mot de passe via `/connexion.html` avec la clé initiale. Après activation, cette clé initiale ne fonctionne plus pour les API. Le mot de passe est dérivé par PBKDF2-HMAC-SHA256 (600 000 itérations, sel aléatoire). La session bearer dure 30 minutes, révocable via le portail ; les modules existants acceptent la clé temporaire copiée manuellement. Le menu du portail est construit selon les permissions ; les permissions restent contrôlées côté serveur. La désactivation ou rotation révoque toutes les sessions du compte. Rotation réinitialise le mot de passe. Les comptes de V12 non activés gardent leur clé de recette. Pas de MFA ni de cookie de session centralisé à ce stade. Le journal des accès est accessible via `/audit.html`.

Docker (configuration à tester sur Docker Desktop / VPS) : créer une clé aléatoire comme indiqué ci-dessous, définir `DSIG_ENV=REC`, puis `docker compose -p dsig-rec up -d --build`. Pour DEV, sélectionner `DSIG_ENV=DEV`, `DSIG_PORT=8081` et `docker compose -p dsig-dev up -d --build` : volumes distincts grâce aux noms de projet. Les ports sont liés à localhost uniquement. Le mode PROD refuse de démarrer. Ne pas exposer le serveur sur Internet. La sauvegarde SQLite et le test de restauration restent nécessaires avant toute migration.

## V12 — Comptes et autorisations

Avec la clé administrateur de recette, ouvrir `/accounts.html`, créer les comptes nominatifs et conserver leur clé aléatoire (affichée une seule fois, empreinte SHA-256 en base). Les clés individuelles sont saisies à la place de la clé d'administration dans chaque module permis ; elles ne sont pas stockées dans le navigateur. Désactivation et renouvellement immédiats pour les requêtes suivantes. La clé administrateur d'environnement reste une clé de secours. Un consultant doit être lié à l'identifiant UUID de son profil (accessible via l'API administrateur consultants) ; il utilise `/my-activity.html` et ne voit que ses propres missions et CRA, sans coûts ni taux commerciaux. Il soumet mais ne valide pas. Les autres rôles ont des droits de lecture/écriture par module, pas de cloisonnement par champ. Le journal autorisations trace l'identifiant, la décision et la ressource, non le succès métier ; pas d'authentification par mot de passe, MFA, sessions expirantes ou audit infalsifiable. Les comptes de recette ne doivent pas être utilisés sur un serveur public.

## V11 — Registre financier interne

`/billing.html` : créer et valider des jalons au forfait, enregistrer des créances HT avec référence et échéance, puis affecter les encaissements partiels ou complets. Les jalons cumulés ne dépassent pas le prix du forfait ; les créances ne dépassent pas les CRA validés (régie) ou jalons validés (forfait). Les paiements ne dépassent pas le solde. Synthèse séparée par devise et détection des retards. Aucun document fiscal, TVA, véritable grand livre, annulation/avoir, règlement bancaire, relance automatique ou export comptable ; les références sont internes et uniques. Utiliser exclusivement des données fictives. Les comptes individuels et la séparation des rôles restent à développer.

## V10 — Missions et CRA

Dans `/missions.html`, sélectionner un devis accepté, un consultant disponible, une référence de contrat et une période. Une seule mission par opportunité et un consultant par mission ; les périodes actives qui se chevauchent sont bloquées. Saisir les CRA quotidiens (maximum un jour travaillé, facturable inférieur ou égal), puis valider ou refuser. Les CRA traités sont immuables ; une mission ne peut être clôturée tant que des CRA sont soumis. Seuls les CRA validés alimentent le coût direct estimé (jours travaillés × coût journalier du devis + frais saisis). En régie, CA facturable = jours facturables × TJM ; au forfait, CA réalisé et marge réelle non calculés tant que la gestion des jalons n'existe pas. Les montants ne sont ni des factures ni des encaissements. La référence contractuelle ne constitue pas un contrat signé. Les corrections de CRA refusés, plusieurs consultants par mission, factures, paiements et comptes individuels restent à développer.

## V9 — Direction et préparation internationale

Le tableau de bord privé `/direction.html` consolide les cinq registres, les relances en retard et les engagements estimés HT par devise. Seuls les devis acceptés uniques par opportunité entrent dans les montants ; les cas ambigus sont signalés et exclus. Aucun chiffre réalisé ou encaissé n'est supposé. La page `/en.html` présente les principales offres en anglais ; le formulaire et les fiches détaillées restent en français.

Sauvegarde SQLite cohérente sans écraser une sauvegarde existante : `python server.py --backup sauvegarde-2026-11-20.sqlite3`. Conserver hors du dossier dist, en lieu sûr et hors du ZIP. Pour tester une restauration, lancer une instance distincte avec DSIG_DB pointant vers une copie de la sauvegarde ; ne pas écraser la base active. Les données ne sont pas chiffrées au repos par SQLite. Cette recette ne remplace pas un audit de sécurité production.

## V7 — CRM commercial

Ouvrir http://127.0.0.1:8080/crm.html avec la clé d'administration.
Les opportunités comprennent le client, le contact, le besoin, les compétences,
le mode de prestation, le statut, les actions de suivi et la date de relance.
La recherche dans le vivier propose les consultants disponibles ; une association
reste visible si le statut du consultant change. Le registre ne crée ni contrat
ni affectation automatique de disponibilité. Les enregistrements et historiques
sont conservés dans SQLite. Les prospects et clients sont identifiés dans les
opportunités ; un référentiel client distinct sera une évolution ultérieure.

## V6 — Vivier de consultants

Ouvrir http://127.0.0.1:8080/consultants.html avec la clé d'administration.
Registre interne de profils, compétences, expérience, mobilité, disponibilité,
statuts, recherche et pagination. Chaque sauvegarde incrémente la version et
historise le statut. Archivage via le statut ARCHIVE, sans suppression.
Utiliser exclusivement des profils fictifs ; aucun CV n'est collecté.
Les candidatures publiques restent dans le registre des demandes ; leur
qualification et création dans le vivier sont manuelles.

## V5 — Avant-vente et appels d'offres

Ouvrir http://127.0.0.1:8080/tenders.html avec la clé d'administration.
Créer et modifier les dossiers, filtrer le pipeline, suivre les échéances
et renseigner les budgets estimatifs par devise. Les étapes sont libres
selon la situation du dossier ; chaque sauvegarde est historisée et protégée
contre les modifications concurrentes. Aucun dépôt de réponse, e-mail ou
collecte externe automatisée n'est réalisé. Les données restent dans SQLite.

## V4 — Vitrine de conseil sans catalogue public

Les 18 expertises disposent de fiches détaillées : objectifs, interventions,
livrables possibles et lien de contact prérempli. Le catalogue de produits
n'est plus présent dans le répertoire servi ni dans le ZIP de recette.
Les anciennes demandes restent accessibles à l'administrateur.
Les secteurs dirigent vers une demande de conseil, non vers les produits.

## V3 — Expertises et talents

18 expertises organisées en quatre pôles, icônes SVG locales sur le catalogue
et les fiches solutions, candidatures spontanées et filtre administratif par
type de demande. Les candidatures sont des expressions d'intérêt pour de
futures missions, et non des annonces d'emploi actives. Aucun CV n'est collecté
en recette ; utiliser des données fictives.

## Démarrage

Dans le dossier du projet :

```powershell
python server.py
```

Ouvrir http://127.0.0.1:8080 dans le navigateur. Le serveur écoute uniquement sur la boucle locale. Utiliser des données fictives : la démonstration réelle d'un SaaS n'est jamais exposée.

## Demandes commerciales

Le formulaire enregistre une demande dans `data/requests.sqlite3` et retourne un identifiant. Aucun e-mail n'est envoyé. La base est exclue de Git et située hors du répertoire web. Pour exporter les demandes, depuis le terminal du propriétaire :

```powershell
python server.py --export
```

Pour créer un CSV, utiliser la redirection de sortie de votre terminal. Protéger ce fichier : il peut contenir des données personnelles. Aucun accès public au registre.

## Recette

```powershell
python -m unittest -v test_server
node --check dist/app.js
node --check dist/solution.js
node --check dist/admin.js
```

## Administration commerciale locale

Dans PowerShell, interrompre le serveur précédent (Ctrl+C) puis générer une clé privée aléatoire pour cette session :

```powershell
$env:DSIG_ADMIN_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:DSIG_ADMIN_TOKEN
python server.py
```

Ouvrir http://127.0.0.1:8080/admin.html. Dans un autre terminal, la variable n'est pas automatiquement disponible : récupérer la clé dans le terminal de lancement avant de démarrer le serveur, avec `$env:DSIG_ADMIN_TOKEN`. Ne jamais la communiquer. Le jeton n'est pas conservé dans le navigateur.

Le tableau de bord permet de filtrer les demandes et de suivre les statuts Nouvelle, Qualifiée, En cours, Gagnée et Perdue. Les transitions sont historisées en base. Le registre n'est accessible qu'avec la clé ; aucune démonstration directe ni notification e-mail.

## Avant production

V16 : le portail de connexion affiche le nombre de sessions actives et l'état MFA. La révocation des autres sessions exige le mot de passe et conserve la session courante. Les déconnexions et révocations sont journalisées.

V15 : ouvrir `connexion.html`, activer le compte individuel puis se connecter. Les modules utilisent la même session navigateur (30 minutes). Pour activer la MFA, confirmer le mot de passe, saisir la clé dans une application TOTP et confirmer le code affiché. Reconnexion avec un nouveau code obligatoire ; attendre le prochain intervalle de 30 secondes. Recette locale uniquement ; voir SECURITY.md.

V8 : depuis l’administration, créer une opportunité CRM puis ouvrir Devis et marges. Rechercher l’opportunité et renseigner les jours, le TJM (régie) ou le prix fixe (forfait), les coûts et frais internes. Tous les calculs HT sont effectués côté serveur en décimal. La marge brute = CA estimé − coûts directs ; elle ne représente pas le résultat net. Les devis acceptés/refusés sont verrouillés. L’export texte exclut les coûts internes ; il doit être vérifié avant transmission. Aucune facturation, fiscalité ou notification automatique. Les prévisions par devis ne doivent pas être additionnées entre devis alternatifs ni devises différentes.

- Recette visuelle et accessibilité sur mobile et ordinateur.
- Revue de sécurité, politique de rétention, traitement et suppression des données.
- Remplacer le serveur Python de recette par une infrastructure de production et mettre en place HTTPS, sauvegardes, supervision, limitation de débit distribué et gestion sécurisée des demandes.
- Vérifier les mentions légales et activer l'indexation uniquement après autorisation.
- En dernier : nom de domaine, e-mails professionnels et notifications.

Ne pas exposer ce serveur local directement sur Internet.
