# V196 — Vérification cryptographique hors ligne

NO GO : aucune autorisation de démarrage ni publication. Le verrou V194 reste intact. Ce lot indépendant de V195 ajoute un vérificateur Ed25519 sans gestion de clé privée ni activation runtime.

Le signataire autorisé devra conserver sa clé privée hors VPS. L'opérateur doit fournir une clé publique de confiance obtenue indépendamment de l'enveloppe et les empreintes exactes établies par une procédure distincte. L'enveloppe contient payload et signature Base64. Le payload schéma 1 est signé sur JSON ASCII trié, compact, sans espaces. Il lie le commit Git, le digest image SHA256, l'empreinte SHA256 de la configuration et du dossier de preuves, le but DSIG-PROD-ISOLATED-REVIEW, les dates UTC d'émission et d'expiration. Durée maximale 24 h.

PASS signifie signature valide et correspondance des valeurs fournies, pas vérité des preuves ni autorisation de production. La fonction retourne toujours production_authorized=false. Pas de clé publique embarquée dans une preuve, pas de secret dans le rapport. Pas de CLI de signature ni de génération de clés pour l'instant.

Restent à concevoir et tester : enrôlement et révocation de la clé de confiance, définition précise des octets de configuration et preuves à hacher sans divulgation, provenance de l'image, protection anti-rejeu et horloge fiable, gouvernance à plusieurs responsables, intégration fail-closed au runtime, revue indépendante G08/G10. Une signature seule ne lève jamais le verrou. Aucun changement VPS, DNS, Caddy, REC ou vitrine.
