# V137 — Coûts affectés aux solutions SaaS

Dans Finance, enregistrer un décaissement réel sans mission, puis affecter tout
ou partie de son montant à un produit du catalogue et à une nature de coût :
infrastructure, support, acquisition, exploitation. La référence du décaissement
est obligatoire. Une seule affectation par dépense, produit et nature ; le
solde disponible ne peut pas être dépassé, même en cas de requêtes concurrentes.
Une dépense affectée à une mission est exclue. Aucun paiement supplémentaire
n'est créé. Les affectations sont historisées et auditées.

ADMIN et COMPTABLE peuvent affecter ; DIRECTION et CONTROLE peuvent consulter.
Les synthèses restent globales depuis l'origine, par devise, sans conversion.
Le flux net affecté est l'encaissement TTC moins les décaissements ventilés.
Il ne représente ni la marge comptable ni le bénéfice : TVA, amortissements,
coûts non ventilés et charges à payer ne sont pas retraités.
Les montants facturés HT restent présentés séparément.

L'historique Finance est paginé à dix lignes avec recherche dynamique.
Le tableau Direction expose seulement les agrégats, pas les références des
dépenses. Aucun déploiement de production ni écriture comptable externe.
