# V197 — Topologie Compose PROD (revue uniquement)

NO GO. compose.prod.yaml est un plan concret de configuration, non un déploiement. Profil prod-review, entrypoint de refus indépendant du serveur V194, restart=no. Ne pas lancer up. Ne pas supprimer le verrou pour essayer la topologie.

Projet dsig-prod, volume dsig-prod_prod-data neuf à vérifier avant création, réseau interne sans edge, port loopback à réserver (ni 8300 ni 8310), UID/GID 10001, montage ClamAV privé en lecture seule, ressources et rotation selon les mesures V192. Le réseau interne bloque les sorties normales ; la future architecture des workers et de l'accès proxy devra être revue. Aucun port, DNS ou proxy n'a été modifié.

DSIG_PROD_IMAGE doit désigner un digest de registre immuable approuvé, et disponible localement (pull_policy never). L'image n'est pas construite ni publiée ici. Les variables dédiées doivent être générées et stockées hors Git lors d'une procédure approuvée, distinctes de REC/candidate. Les expressions Compose vérifient seulement la présence, pas la qualité. V195 contrôle les valeurs hors ligne. Le validateur de configuration résolue et l'attestation de provenance restent à construire. Ne jamais afficher le JSON résolu qui contient les secrets.

La CI utilise exclusivement des valeurs fictives et vérifie la topologie sans lancer de conteneur PROD. Le healthcheck de la future image reste hérité du Dockerfile ; aucun healthcheck PROD fonctionnel n'est attesté. Le domaine app est proposé, pas publié ; le domaine client séparé nécessite une évolution des règles d'origine. Aucun volume existant n'est importé, aucune procédure d'ouverture n'est fournie. Prochaine étape : validation stricte du Compose résolu, provenance des digests et confiance cryptographique avant intégration runtime.
