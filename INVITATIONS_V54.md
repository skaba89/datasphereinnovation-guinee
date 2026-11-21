# V54 — Invitations de test REC

Dans Comptes, créer un compte fictif non activé puis cliquer Invitation REC. La clé initiale reste à transmettre séparément ; le message ne contient ni identifiant personnel ni secret. Un seul envoi par compte, avec retries bornés et idempotence. L'état ACCEPTED signifie accepté par Resend et non livré. Les comptes activés ou désactivés sont exclus du traitement en attente.

Après déploiement REC, installer les deux unités dsig-rec-invitations.service et .timer dans /etc/systemd/system, daemon-reload puis enable --now dsig-rec-invitations.timer. Le worker reprend la configuration root /etc/dsig-rec-contact.json existante. Aucun destinataire saisi par le navigateur. Ne pas activer en PROD.

Recette : créer un compte COMMERCIAL fictif, demander l'invitation, vérifier PENDING puis ACCEPTED, contrôler la boîte de test et l'absence de secret. Le compte doit ensuite être activé avec sa clé initiale sur le portail. Une invitation répétée est refusée. Aucun envoi réel collaborateur dans cette version.
