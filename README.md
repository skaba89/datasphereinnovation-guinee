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

V23.2 : Direction propose un reporting mensuel sur une plage inclusive de 366 jours maximum, exportable en CSV UTF-8. Les CRA validés sont imputés à leur date de travail, les jalons forfaitaires à leur événement de validation, les créances à leur date de saisie et les flux à leur date effective. Les devises ne sont jamais additionnées. Les cumuls mensuels peuvent différer du cumul global par les arrondis ; les données reflètent les statuts actuels et ne sont pas des arrêtés historiques. L’export est protégé par les mêmes permissions que Direction, sans données nominatives.

V23.1 : Finance enregistre les décaissements effectivement payés, par référence unique, devise, date, catégorie et mission facultative. Le flux net enregistré = encaissements affectés moins décaissements enregistrés, sans solde initial ni rapprochement bancaire. Ces sorties ne sont pas additionnées aux coûts CRA pour éviter le double comptage. Direction affiche les coûts individuels et la marge en régie par consultant et mission ; en forfait, la recette et la marge individuelles ne sont pas attribuées. Les dépenses sont immuables dans cette version ; correction/contrepassation à traiter ultérieurement.

V23 : dans Direction, le contrôle de gestion compare le budget du devis accepté effectivement affecté à chaque mission aux CRA et jalons validés. Synthèses par devise, client et mission ; les organisations liées au CRM sont regroupées par identifiant, les anciens libellés exacts restent distincts. Les coûts consommés, écarts budgétaires, créances, encaissements, retards et montants validés non facturés sont des indicateurs opérationnels cumulés, pas un bilan comptable ni une trésorerie nette. Le filtre de recherche agit sur les listes client et mission, pas sur les totaux globaux par devise.

V22.2 : le bouton Contrat / renouvellement affiche la référence initiale, l’échéance et l’historique des demandes. Le chef de projet ou l’administrateur soumet une prolongation avec référence d’avenant et motif ; un administrateur distinct valide ou refuse. L’échéance n’est prolongée qu’après validation et contrôle de disponibilité de toute l’équipe. Les tarifs et la référence du contrat initial ne changent pas. Il s’agit d’un registre interne, pas d’une signature électronique ni d’une notification automatique. Une demande en attente empêche la clôture de la mission.

Avant la mise à niveau V22.1, conserver une sauvegarde et la version du code correspondante. Une sauvegarde antérieure doit être restaurée dans une instance isolée de sa version d'origine, puis migrée avant utilisation avec V22.1.

Dans `/missions.html`, sélectionner un devis accepté, un consultant disponible, une référence de contrat et une période. Une seule mission par opportunité et depuis V22.1 plusieurs consultants par mission ; les périodes actives qui se chevauchent sont bloquées. Saisir les CRA quotidiens par consultant (maximum un jour travaillé, facturable inférieur ou égal), puis valider ou refuser. Les CRA traités sont immuables ; une mission ne peut être clôturée tant que des CRA sont soumis. Seuls les CRA validés alimentent le coût direct estimé (jours travaillés × coût journalier du devis + frais saisis). En régie, CA facturable = jours facturables × TJM ; au forfait, CA réalisé et marge réelle non calculés tant que la gestion des jalons n'existe pas. Les montants ne sont ni des factures ni des encaissements. La référence contractuelle ne constitue pas un contrat signé. Les corrections de CRA refusés, restent à développer. Les membres sont affectés sur toute la période de mission ; les tarifs du devis sont communs à l’équipe. Les anciens CRA sont rattachés automatiquement au consultant principal lors de la migration.

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
opportunités. Depuis V22, le référentiel CRM permet de créer et modifier les
prospects, clients et partenaires, de rechercher par nom et de rattacher une
opportunité à une organisation. Le libellé historique reste inchangé ; les
anciennes opportunités ne sont pas rattachées automatiquement. Les doublons de
nom normalisé et les modifications concurrentes sont refusés. Les permissions
CRM existantes s'appliquent aussi au référentiel.

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

## V73 — Catalogue commercial interne

Le CRM contient un catalogue réservé aux rôles habilités au CRM (administration, direction, commercial). Guinée Logistique est explicitement classé prototype de démonstration : données fictives uniquement, persistance et autorisations serveur à industrialiser avant pilote. Les autres solutions sont documentées sans promesse de disponibilité. Aucun lien de démonstration public ni changement du site vitrine.

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

V21 : couche d'accessibilité commune aux 16 pages (lien d'évitement, focus visible, défilement horizontal des tableaux au clavier, réduction des animations, formulaires adaptés au mobile). Police système et ressources locales uniquement, CSP sans dépendance Internet. Tests Playwright sur menu mobile, navigation clavier et débordement horizontal. Ces tests ne constituent pas une certification WCAG ni un benchmark complet de performance.

V20 : voir `OPERATIONS.md` pour les sauvegardes chiffrées, la restauration isolée, les contrôles SQLite et la supervision locale. Le point `/api/ready` vérifie la disponibilité du schéma de la base sans la créer ; Docker l'utilise comme healthcheck. La sauvegarde historique `--backup` reste disponible en clair pour compatibilité ; privilégier `--backup-encrypted`. Ne jamais stocker les clés dans Git.

V19.1 : cinq pôles d'expertise et 25 fiches détaillées, dont sept spécialités cybersécurité et résilience supplémentaires, avec formulaire prérempli, qualification des demandes et profils cyber dans le vivier. Les prestations spécialisées sont à cadrer selon les ressources mobilisables et les autorisations ; aucune certification, service SOC 24/7 ou habilitation n'est revendiqué.

V19 : tests navigateur locaux avec `python -m pip install -r requirements-dev.txt`, `python -m playwright install chromium`, puis `python -m unittest -v browser_e2e`. Ils démarrent un serveur loopback sur port aléatoire et une base temporaire, sans données réelles. Le job CI browser-acceptance exécute les mêmes parcours. Le compte administrateur affiche dix espaces métier ; Mes CRA est réservé aux consultants associés.

V18 : la MFA devient obligatoire pour ADMIN, DIRECTION, CONTROLE, COMPTABLE et AUDITEUR. Après connexion par mot de passe, ces comptes n'ont accès qu'au portail d'inscription MFA tant que le second facteur n'est pas activé ; les API métier refusent également les clés initiales. ADMIN est toujours obligatoire ; DSIG_MFA_REQUIRED_ROLES personnalise les autres rôles (valeur par défaut : DIRECTION,CONTROLE,COMPTABLE,AUDITEUR). Configurer DSIG_MFA_KEY avant l'inscription. La clé bootstrap reste un accès d'administration d'urgence propre à la recette locale et doit être supprimée ou strictement contrôlée avant production.

V17 : installer les dépendances avec `python -m pip install -r requirements.txt`. Générer une seule fois une clé Fernet avec `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` et la conserver dans la variable d'environnement `DSIG_MFA_KEY` (ou dans le fichier .env local non versionné pour Docker). Ne jamais la publier ni la régénérer à chaque démarrage. Sans clé valide, les opérations MFA échouent sans contourner la protection. À l'activation MFA, conserver les huit codes de secours hors ligne ; chacun ne peut servir qu'une fois avec le mot de passe. Pour les comptes MFA V15/V16, une authentification TOTP réussie migre le secret vers le format chiffré ; une rotation administrative suivie d'une nouvelle activation permet d'obtenir les codes de secours. Faire une sauvegarde avant migration et conserver la clé séparément.

V16 : le portail de connexion affiche le nombre de sessions actives et l'état MFA. La révocation des autres sessions exige le mot de passe et conserve la session courante. Les déconnexions et révocations sont journalisées.

V15 : ouvrir `connexion.html`, activer le compte individuel puis se connecter. Les modules utilisent la même session navigateur (30 minutes). Pour activer la MFA, confirmer le mot de passe, saisir la clé dans une application TOTP et confirmer le code affiché. Reconnexion avec un nouveau code obligatoire ; attendre le prochain intervalle de 30 secondes. Recette locale uniquement ; voir SECURITY.md.

V8 : depuis l’administration, créer une opportunité CRM puis ouvrir Devis et marges. Rechercher l’opportunité et renseigner les jours, le TJM (régie) ou le prix fixe (forfait), les coûts et frais internes. Tous les calculs HT sont effectués côté serveur en décimal. La marge brute = CA estimé − coûts directs ; elle ne représente pas le résultat net. Les devis acceptés/refusés sont verrouillés. L’export texte exclut les coûts internes ; il doit être vérifié avant transmission. Aucune facturation, fiscalité ou notification automatique. Les prévisions par devis ne doivent pas être additionnées entre devis alternatifs ni devises différentes.

- Recette visuelle et accessibilité sur mobile et ordinateur.
- Revue de sécurité, politique de rétention, traitement et suppression des données.
- Remplacer le serveur Python de recette par une infrastructure de production et mettre en place HTTPS, sauvegardes, supervision, limitation de débit distribué et gestion sécurisée des demandes.
- Vérifier les mentions légales et activer l'indexation uniquement après autorisation.
- En dernier : nom de domaine, e-mails professionnels et notifications.

Ne pas exposer ce serveur local directement sur Internet.
### Coffre documentaire V24 (recette)

Le portail administrateur permet de déposer et télécharger des PDF fictifs associés aux missions, consultants, devis et dépenses par leur UUID. Le contenu est chiffré avec Fernet, distinct de la clé MFA ; les métadonnées restent en clair. Générer localement `DSIG_DOCUMENT_KEY` avec `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`, puis l'injecter hors Git. Conserver cette clé séparément des sauvegardes ; sans elle, les documents ne sont pas récupérables. Les anciens backups doivent être restaurés avec la version d'origine avant migration. Dépôts et téléchargements sont journalisés, quota 20 Mio, 1 Mio par PDF. Pas de prévisualisation, d'antivirus, de purge ni de rotation de clé à ce stade : usage fictif uniquement, pas de données personnelles réelles.

### V24.1 — Alertes métier

Le portail ADMIN et DIRECTION contient un centre d'alertes calculé à la consultation : contrats actifs et relances ouvertes à échéance dans les 30 jours ou en retard, factures non soldées, CRA soumis et renouvellements en attente. Les éléments résolus disparaissent au prochain rafraîchissement. Filtres par catégorie et priorité. Aucun e-mail, SMS, tâche planifiée ou donnée réelle ; ces intégrations restent à valider séparément.

### V24.2 — Historique et rotation documentaire

Une nouvelle version référence la précédente (même catégorie et dossier), sans écraser les PDF historiques. La date facultative de revue indique les documents à examiner ; aucune suppression automatique, aucun délai légal présumé. La rotation utilise une nouvelle clé `DSIG_DOCUMENT_KEY` et temporairement `DSIG_DOCUMENT_PREVIOUS_KEY`. Serveur arrêté, réaliser une sauvegarde chiffrée, restaurer une copie isolée hors `dist`, puis lancer `python server.py --rotate-documents /chemin/copie.sqlite3`. La transaction vérifie chaque contenu et annule tout en cas d'erreur. Vérifier la copie, tester les téléchargements avec la nouvelle clé seule avant toute promotion contrôlée ; conserver l'ancienne clé pour les anciennes sauvegardes. Aucun remplacement de la base active par la commande. Antivirus et politique de purge restent à définir avant usage réel.

### V24.3 — Notifications internes et rappels programmables

Lancer `python server.py --refresh-notifications` en DEV/REC ou `docker compose exec -T dsig python server.py --refresh-notifications`. Un traitement transactionnel déduplique les rappels par type, dossier, échéance et priorité ; le passage en retard crée un nouveau rappel. Les rappels résolus ou remplacés passent en historique. ADMIN et DIRECTION disposent d'un statut de lecture individuel. Planification quotidienne possible via cron sur le VPS (exemple `0 8 * * * cd /chemin/recette && docker compose exec -T dsig python server.py --refresh-notifications`, à adapter au fuseau du serveur et au projet). Aucun cron installé ni e-mail/SMS diffusé par cette version. Le portail affiche les résultats du dernier traitement ; les alertes dynamiques restent disponibles.

### V24.4 — Contrôle antivirus obligatoire

La GED utilise ClamAV via le protocole `INSTREAM` sur socket Unix privé. Configurer `DSIG_CLAMD_SOCKET` (chemin absolu) ; en Docker, utiliser `docker compose -f compose.yaml -f compose.antivirus.yaml up -d` avec `DSIG_CLAMD_SOCKET_DIR` pointant vers le répertoire privé du socket hôte `clamd.sock`. Configurer les permissions pour l'UID 10001, sans socket TCP public ; maintenir les signatures à jour avec freshclam. Configurer les limites du daemon au-dessus de 1 Mio et le refus des documents chiffrés/non inspectables (AlertEncrypted et AlertExceedsMax). Vérifier ces réglages sur le vrai daemon avant toute recette réelle.

Chaque dépôt et téléchargement (y compris les anciens documents) doit recevoir une réponse propre du scanner ; détection = HTTP 422, indisponibilité ou réponse inattendue = HTTP 503. Aucun fichier refusé n'est enregistré ni servi. Le contenu transite en mémoire, sans fichier temporaire ; les refus sont journalisés sans contenu ni signature. Le scanner est limité à quatre appels simultanés et quinze secondes par appel. Les tests locaux simulent le daemon ; la validation avec ClamAV réel et test antivirus inoffensif reste obligatoire avant production. Le domaine cible est `dsig-consulting.com` ; aucun DNS ou déploiement n'est modifié ici.

