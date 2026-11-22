# V155 — Journal et gouvernance

Le journal ADMIN/AUDITEUR affiche dix événements par défaut, avec pagination serveur (10, 25, 50 ou 100), recherche littérale sur acteur/action/ressource et filtre des décisions d'autorisation. Une borne d'identifiant fixe la vue durant la navigation pour éviter les doublons dus aux nouvelles écritures, y compris les consultations du journal elles-mêmes. Actualiser ouvre une nouvelle vue ; les contrôles de rôle sont toujours calculés à date. L'API sans paramètre conserve une limite de 100 événements.

La synthèse des habilitations agrège les comptes actifs, activés et enrôlés MFA par rôle, avec l'obligation MFA effective. Elle ne divulgue ni clés, ni secrets, ni mots de passe. Elle ne constitue pas une preuve de conformité réglementaire, ni une certification d'audit indépendant. Le journal SQLite reste modifiable par un administrateur de stockage ; une externalisation inviolable et une politique de conservation approuvée restent à prévoir avant production.

La consultation ne modifie pas les comptes. Elle conserve la journalisation des autorisations existante. Aucun changement VPS ni activation automatique de production.
