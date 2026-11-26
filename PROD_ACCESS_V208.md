# V208 — Refus du bootstrap HTTP et des Bearer bruts hors DEV/REC

accounts.authorize refuse avant accès à la base tout appel hors DEV/REC qui n'utilise pas le mode de session cookie nominatif. Le jeton bootstrap est neutralisé dans ces modes, même si la variable est présente. Les comportements DEV/REC sont conservés. Les règles existantes de session, rôle, MFA et origine continuent de s'appliquer. Le serveur reste verrouillé en PROD.

Ce lot ne qualifie pas toutes les routes d'authentification, la délivrance des cookies, la récupération MFA ni les autres points d'entrée. L'absence de jeton bootstrap dans la configuration cible nécessite encore une révision coordonnée des validateurs V195–V205. Les tests n'activent pas le serveur PROD. Aucun déploiement.
