# V47 — Notifications commerciales REC

Chaque nouvelle demande REC crée deux entrées transactionnelles dans `contact_mail` (notification interne et accusé FR/EN). Les anciennes demandes ne sont pas reprises. Aucun envoi n'est effectué par la requête HTTP.

Le worker est désactivé tant qu'il n'est pas lancé. En REC, les deux messages vont uniquement vers une adresse de test contrôlée, sans nom, adresse ou contenu du prospect. Le verrou PROD reste inchangé. Créer une clé Resend dédiée, limitée à l'envoi du domaine vérifié. Ne pas réutiliser la clé des alertes techniques.

Sur le VPS, créer `/etc/dsig-rec-contact.json` avec `sudo install -m 600 /dev/null /etc/dsig-rec-contact.json` (uniquement si absent), puis `sudoedit /etc/dsig-rec-contact.json`. Format :

```json
{"api_key":"re_REMPLACER","sender":"notifications@dsig-consulting.com","test_recipient":"REMPLACER_PAR_VOTRE_BOITE_DE_TEST"}
```

Depuis `/home/ubuntu/datasphereinnovation-guinee`, après déploiement REC :

```bash
sudo cat /etc/dsig-rec-contact.json | docker compose -p dsig-rec -f compose.yaml -f compose.rec-edge.yaml -f compose.rec-clamav.yaml exec -T dsig python server.py --send-contact-notifications
docker compose -p dsig-rec -f compose.yaml -f compose.rec-edge.yaml -f compose.rec-clamav.yaml exec -T dsig python server.py --contact-mail-status
```

Soumettre une demande fictive FR et EN, puis lancer le worker. Vérifier les quatre messages de test et les références dans le CRM. `ACCEPTED` signifie accepté par Resend, pas livré. Vérifier la réception effective dans la boîte et le dashboard Resend. Les erreurs sont retentées avec temporisation, au plus cinq tentatives et avant 20 heures; les clés d'idempotence Resend sont valides 24 heures. Les entrées expirées ou définitivement échouées restent traçables. Ne pas rejouer automatiquement une sauvegarde restaurée.

Après validation du test manuel, installer le service et timer ci-dessous avec les unités existantes, puis activer le timer. Ne pas les installer sur un candidat isolé.
