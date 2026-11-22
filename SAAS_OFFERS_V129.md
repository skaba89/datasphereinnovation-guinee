# V129 — Brouillons d'offres SaaS personnalisées

Dans le CRM privé REC, renseigner le simulateur tarifaire puis choisir une opportunité à l'aide de la recherche dans Offres SaaS. Saisir l'intitulé et la date de validité (aujourd'hui ou ultérieure), puis enregistrer le brouillon. Le montant est recalculé côté serveur sans accepter de totaux fournis par le navigateur.

Le registre paginé conserve un instantané des paramètres, des montants HT, de l'opportunité, de l'auteur et de la date de création. L'événement d'enregistrement est journalisé. Toute nouvelle simulation enregistrée crée un nouveau brouillon indépendant, sans modifier les précédents. Les montants et devises ne sont pas agrégés ici.

Les autorisations CRM existantes sont réutilisées : accès en lecture pour les rôles autorisés, écriture pour les rôles pouvant modifier le CRM. Les archives SQLite incluent la table additive `saas_offers`. Aucun abonnement, contrat, facture, revenu comptabilisé, transmission automatique ou changement de statut de l'opportunité n'est créé. Aucun tarif officiel ni GO PROD.

Recette : créer une opportunité fictive, enregistrer un scénario et vérifier son total et ses paramètres dans le registre. Enregistrer un autre tarif et vérifier que le premier instantané ne change pas. Tester les dates passées et les identifiants inconnus, ainsi que les accès non autorisés.
