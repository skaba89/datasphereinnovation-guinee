# V126 — Conversion d'un prospect en client

Dans le CRM privé REC, créer ou sélectionner une organisation de type PROSPECT, rattacher une opportunité et enregistrer son statut gagné (GAGNE, EN_MISSION ou TERMINE). Dans le référentiel, le nombre d'opportunités gagnées est affiché. L'action Convertir en client nécessite une confirmation explicite.

La conversion transactionnelle conserve le même identifiant, les notes et tous les liens existants. Elle incrémente la version et enregistre l'auteur, la date et une opportunité gagnée justificative, ainsi qu'un événement dans le journal des accès. Elle refuse une version obsolète, une organisation non prospect ou une absence d'opportunité gagnée. Le changement direct PROSPECT vers CLIENT dans le formulaire générique est refusé : utiliser l'action dédiée. Les autres reclassements et la création de clients existants restent possibles dans le référentiel.

Le statut de l'opportunité n'est pas modifié. Aucun contrat, abonnement, paiement ou message n'est créé automatiquement. L'historique de conversion est conservé dans SQLite et inclus dans les sauvegardes. La création de la table est additive, sans suppression ou réécriture des données précédentes.

Recette : vérifier le refus avant gain, enregistrer une opportunité gagnée, confirmer la conversion, vérifier le type CLIENT, les liens et l'audit ; tester le refus d'une répétition et d'une version obsolète. Données fictives uniquement. Aucun GO PROD.
