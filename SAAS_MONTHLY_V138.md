# V138 — Performance mensuelle SaaS

Finance et Direction proposent une synthèse de 1 à 24 mois inclusifs,
filtrable par produit et devise, avec pagination de 10 lignes et export CSV
de tout le résultat filtré. Les mois sans mouvement ne sont pas affichés.

La facturation HT est rattachée au mois d'émission, les règlements TTC au
mois de réception et les coûts ventilés au mois du décaissement d'origine.
Une affectation tardive peut donc compléter une période antérieure.
Le flux net affecté n'est pas une marge comptable. Aucune conversion de devise,
projection, écriture comptable ni modification des données sources.

API GET /api/admin/billing/saas-monthly et /api/admin/direction/saas-monthly :
start et end au format AAAA-MM, product et currency facultatifs. Chaque
route respecte les droits de son module, notamment AUDITEUR en Direction.
Les anciennes synthèses globales restent inchangées.
