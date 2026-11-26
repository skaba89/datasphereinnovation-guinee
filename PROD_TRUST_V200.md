# V200 — Registre de confiance PROD, revue hors ligne

Le registre JSON est épinglé par SHA256 sur ses octets exacts. L'empreinte attendue doit être obtenue d'une source indépendante et protégée par l'opérateur ; elle ne doit jamais être fournie par l'enveloppe signée. Les identifiants sont les SHA256 des 32 octets de clé publique Ed25519. Le registre impose une période de confiance et un indicateur de révocation ; une clé révoquée est refusée même si sa signature est valide. La période entière de l'autorisation doit être incluse dans celle de la clé.

L'enveloppe V200 ajoute key_id à payload et signature V196. Aucune clé privée n'est stockée ni générée par ce module. Les tests créent uniquement des clés éphémères fictives.

Limites : l'épinglage ne prouve pas à lui seul la provenance du registre ni sa fraîcheur. La procédure d'enrôlement hors VPS, la mise à jour atomique de l'empreinte, la prévention du retour vers un ancien registre, la rotation, le quorum humain et l'anti-rejeu restent à concevoir. Aucune intégration runtime, aucun démarrage, aucune publication. Le retour production_authorized reste false même en cas de PASS.

Ne pas créer de registre réel avant validation de la gouvernance et des procédures de conservation. NO GO maintenu.
