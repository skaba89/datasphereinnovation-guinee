# V49 — Recette de livraison des emails

La file V48 distingue acceptation API et échec d'envoi. V49 ajoute un rapprochement local, sans modifier le worker ni élargir les droits de la clé Resend. Aucune exposition publique supplémentaire. Les preuves sont saisies manuellement par l'opérateur depuis le dashboard Resend; aucune livraison n'est déduite d'un HTTP 200.

Depuis le VPS, après déploiement REC :

```bash
docker compose -p dsig-rec -f compose.yaml -f compose.rec-edge.yaml -f compose.rec-clamav.yaml exec -T dsig python contact_delivery.py status
```

Dans https://resend.com/emails, rechercher le `provider_id` et vérifier le statut exact. Si réellement livré, saisir (remplacer ID par le provider_id réel) :

```bash
docker compose -p dsig-rec -f compose.yaml -f compose.rec-edge.yaml -f compose.rec-clamav.yaml exec -T dsig python contact_delivery.py record ID delivered
```

Autres événements possibles : `sent`, `delivery_delayed`, `bounced`, `complained`, `failed`, `suppressed`. Ne pas enregistrer d'événement non observé. La répétition est idempotente; les échecs terminaux priment sur la livraison et les retards. Les états du worker restent indépendants. Aucun contenu ou destinataire n'est affiché. Le suivi automatique par webhook signé nécessite une route dédiée et une revue de sécurité; il n'est pas activé ici.
