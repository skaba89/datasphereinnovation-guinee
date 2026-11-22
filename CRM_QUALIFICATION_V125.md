# V125 — Qualification commerciale et suivi des démonstrations

Dans le CRM privé REC, chaque opportunité possède quatre critères : besoin, budget, décideur et échéance. Pour chacun, choisir À confirmer, Non ou Oui. Le score correspond uniquement au nombre de Oui sur quatre ; ce n'est ni une probabilité de vente ni une décision automatique. Le statut commercial reste indépendant.

La démonstration peut être non demandée, demandée, planifiée, réalisée ou annulée. Une date est obligatoire pour les états planifiée et réalisée et interdite pour non demandée. Aucun rendez-vous ni message externe n'est envoyé automatiquement.

Le registre affiche le score et l'état de la démonstration. Modifier une opportunité permet de retrouver les valeurs conservées. Les dossiers historiques commencent avec les quatre critères à confirmer et aucune démonstration demandée. Les anciennes requêtes API restent compatibles et ne modifient pas la qualification si le champ est absent. La mise à jour conserve le contrôle de version et les autorisations CRM existantes.

La table additionnelle est créée sans modifier les lignes historiques et fait partie de la sauvegarde SQLite. Avant activation REC, vérifier la CI exacte et effectuer la sauvegarde et une restauration isolée. Utiliser uniquement des données fictives. Aucun GO PROD.

Recette : créer une opportunité fictive, confirmer deux critères, planifier une démonstration, enregistrer et rouvrir. Vérifier le score 2/4, la date, le refus d'une date incohérente et l'affichage mobile. Les tests API couvrent aussi le conflit de version et la compatibilité des anciens clients.
