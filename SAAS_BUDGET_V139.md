# V139 — Objectifs et budgets SaaS

Finance : ADMIN et COMPTABLE définissent une cible mensuelle de facturation
HT et un budget de coûts décaissés affectés par produit et devise.
Chaque enregistrement crée une révision auditée ; la dernière fait foi.
Un zéro explicite est distinct de l'absence de budget.

Finance et Direction : comparaison du réalisé V138 avec les objectifs,
écart de facturation, budget restant, taux d'atteinte (non applicable si
objectif nul), signal visuel si les coûts excèdent le budget.
Pour une synthèse annuelle, sélectionner janvier à décembre : les totaux
comparent exclusivement les mois budgétés, sans inventer les cibles absentes.
Les devises restent séparées. L'export CSV mensuel inclut les écarts.

Les routes existantes conservent leurs permissions. Le rôle AUDITEUR
consulte les agrégats Direction mais ne peut écrire ni accéder à Finance.
Aucune écriture comptable ni modification des décaissements.
