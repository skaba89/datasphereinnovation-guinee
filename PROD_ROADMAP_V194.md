# V194 — Première étape du chantier PROD métier

NO GO : aucune autorisation de production, aucun déploiement.

Base main : acf4fda76929af71a7c4d8a5d14d0734abd32e67. La V192 est qualifiée en REC ; ses preuves ne qualifient pas ce nouveau SHA.

## Écart corrigé
Le contrôle du mode était situé après connect() pour le serveur et après plusieurs branches CLI. Un mode PROD ou inconnu pouvait donc créer une base, migrer ou tenter une opération CLI avant refus. Le verrou est désormais évalué après parsing et avant toute opération. DEV/REC restent inchangés. Tests sur 15 entrées et trois modes non autorisés.

## Architecture à implémenter par lots
Projet dsig-prod distinct, volume neuf, port loopback réservé après inventaire, image immuable, UID 10001, réseau privé, clés séparées, ClamAV obligatoire, 2 CPU / 512 Mio provisoires, rotation 5 x 10 Mio. Vitrine inchangée. app et client sous dsig-consulting.com proposés ; le code actuel ne supporte qu'une origine HTTPS explicite : séparation des origines à concevoir et tester avant publication. Aucun DNS ni Caddy modifié.

## Matrice de travail (pas une autorisation)
| Gate | État | Responsable à désigner | Travail restant |
|---|---|---|---|
| G01 | PARTIEL | QA | CI exacte du futur SHA |
| G02 | PARTIEL | Métier | V38 et parcours complets |
| G03 | PARTIEL | Sécurité | MFA réel TLS et isolation |
| G04 | PARTIEL | SRE | Chaîne PROD indépendante |
| G05 | PARTIEL | SRE | RPO/RTO acceptés et restauration PROD |
| G06 | PARTIEL | Exploitation | Supervision externe, réception alerte |
| G07 | PARTIEL | SRE | Charge prolongée représentative |
| G08 | NOT_RUN | Auditeur indépendant | Revue sécurité et secrets |
| G09 | PARTIEL | Exploitation | PRA indépendant et rollback données |
| G10 | NOT_RUN | Direction | Autorisation explicite et juridique |

Les preuves REC (cycle B2, restauration, charge, monitoring) restent des preuves REC. Le registre déclaratif ne doit jamais déverrouiller le serveur. Prochain lot : politique de configuration et autorisation cryptographiquement vérifiable, bootstrap nominatif, puis qualification isolée avant toute exposition. Aucun contournement par changement de DSIG_ENV.
