# V143 — Satisfaction et tickets clients

Registre interne CRM, lié à l'identifiant d'une organisation cliente. ADMIN et
COMMERCIAL ouvrent et résolvent un ticket ; lecture selon les permissions CRM
et Direction. L'échéance est la date convenue de résolution (jour civil,
inclusif), non une promesse de disponibilité ni un SLA horaire. Résolution
versionnée, audit des actions, aucun envoi de message.

Une résolution peut consigner des réponses effectivement reçues : CSAT 1 à 5,
NPS 0 à 10. Valeurs absentes exclues des dénominateurs. CSAT = % de réponses 4–5 ;
NPS = % promoteurs (9–10) moins % détracteurs (0–6). Échantillons affichés.
Le risque est un signal simple (ticket ouvert en retard ou CSAT <= 2 historique),
pas un score prédictif. Les mesures sont cumulées sur les tickets enregistrés.

Recherche et pagination de 10 tickets. Le suivi de plans d'amélioration,
ventes additionnelles et enquêtes autonomes est prévu dans une version suivante.
Aucune notification ni modification de facturation.
