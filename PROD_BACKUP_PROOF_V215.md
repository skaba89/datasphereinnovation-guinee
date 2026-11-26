# V215 — Qualification des octets exportés

Avant toute écriture distante, export_review authentifie les octets exacts chargés en mémoire avec la clé Fernet fournie par l'appelant. La base déchiffrée est vérifiée dans un répertoire temporaire privé (schéma requis, intégrité, clés étrangères, révocation des sessions sur la copie). La clé n'est jamais transmise à l'adaptateur. Les tests utilisent le schéma réel et une clé éphémère. Une archive non chiffrée, altérée, de mauvaise clé ou de schéma invalide est refusée. Le retour restore_verified désigne ce contrôle local uniquement.

Limites : la clé doit être obtenue indépendamment de la REC, la provenance du volume et la fraîcheur de l'archive doivent encore être attestées ; le chiffrement seul ne prouve pas l'origine PROD. L'adaptateur distant est toujours fictif dans les tests ; aucun bucket, timer ni export réel. La limite 64 Mio reste inchangée et la mémoire nécessaire doit être qualifiée. Aucun changement REC ou démarrage PROD.
