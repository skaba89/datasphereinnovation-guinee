# V88 — Contrôle consolidé REC

Depuis le checkout du SHA approuvé sur le VPS, après vérification de sa CI :

```bash
cd /home/ubuntu/datasphereinnovation-guinee
python3 scripts/rec-preflight.py "$(git rev-parse HEAD)"
```

Les quatre contrôles existants (version déployée, preflight, monitoring, scanner réel) sont exécutés et synthétisés dans un JSON. WARN, commande en échec, réponse invalide et SHA différent sont bloquants. Le code retour vaut 1 si un contrôle échoue. Le scanner utilise uniquement ses échantillons de test inoffensifs. Aucun redémarrage, installation, changement de configuration ou sauvegarde déclenchée. Le rapport ne reprend pas les sorties brutes ni les secrets.

Un PASS technique ne constitue pas une autorisation PROD. Conserver le rapport hors Git et poursuivre les preuves manuelles V87, notamment restauration hors site, TLS, MFA et recette métier. Le script ne vérifie pas lui-même la CI distante.
