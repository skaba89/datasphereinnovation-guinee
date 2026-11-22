# V142 — Renouvellements SaaS

Le CRM calcule à la consultation les contrats commencés, à échéance entre J et J+90,
sans successeur enregistré ni résiliation. J-90, J-60, J-30 et J-7 sont des seuils
inclusifs : le seuil applicable est le plus proche de l'échéance. Un contrat à
J-30 ou moins sans relance du seuil courant est signalé à risque commercial
(heuristique, pas une prédiction de churn ni de solvabilité).

ADMIN et COMMERCIAL peuvent consigner une relance par contrat et seuil, avec note,
auteur et date. Les doublons et seuils obsolètes sont refusés. Les relances sont
des comptes rendus internes : aucun courriel, SMS ou message n'est envoyé.
La liste est recalculée lors de la consultation ou de l'actualisation ; pas de
tâche de fond ni de notification externe.

La Direction dispose d'un total d'ARR exposé par devise. Il reprend les montants
annualisés contractuels des abonnements concernés, sans conversion de devises,
probabilité de renouvellement ni garantie de recette. Il n'est pas un chiffre
d'affaires prévisionnel signé.

Recherche dynamique, filtre risque et pagination de dix contrats. Accès selon
les permissions CRM/Direction. Recette et sauvegarde préalable avant déploiement.
