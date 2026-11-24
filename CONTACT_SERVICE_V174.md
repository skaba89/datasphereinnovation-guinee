# V174 — Service de contact PROD (issue #156, étape 1/2)

Service minimal qui recevra les demandes du formulaire public. **Livré fermé** : il refuse toute demande (503) tant que l'opérateur n'a pas positionné `DSIG_CONTACT_ENABLED=1`, ce qui n'est autorisé qu'après les validations V161 et les approbations humaines.

## Architecture (décision technique)

```
Visiteur ──HTTPS──> Caddy partagé (inchangé) ──> conteneur vitrine (Caddy interne de l'image)
                                                     ├─ fichiers statiques
                                                     └─ POST /api/contact ──réseau edge──> dsig-contact:8090
```

- **Aucune modification du proxy partagé** : la route sera ajoutée au Caddyfile *interne* de l'image publique (étape 2, uniquement si le formulaire est activé à la construction).
- **Aucun lien avec la REC** : image séparée (`Dockerfile.contact`) contenant uniquement `contact_service.py` et `contact_form.py` ; base séparée (volume `dsig-contact-data`) ; aucune API d'administration exposée.
- Validation identique à la REC (module partagé `contact_form.py`), restreinte aux types publics : devis, démonstration, partenariat, conseil & expertise, formation, autre.

## Sécurité et données

| Exigence #156 | Mise en œuvre |
|---|---|
| Validation serveur | `contact_form.validate`, JSON uniquement, 8 Ko max, champs connus seulement |
| Anti-spam / abus | Pot de miel (réponse neutre, rien stocké), 5 demandes / visiteur / 10 min, 60 / heure au total, doublon (même e-mail + message sous 10 min → même référence) |
| Vrai client derrière proxy de confiance | `X-Forwarded-For` lu à `DSIG_TRUSTED_HOPS` (2 = proxy partagé + vitrine) depuis la droite ; valeur falsifiée en tête ignorée |
| CSRF / origine | `Origin` exactement égale à `DSIG_CONTACT_ORIGIN`, refus `Sec-Fetch-Site: cross-site` |
| Stockage chiffré | Données personnelles chiffrées (Fernet, `DSIG_CONTACT_KEY`) ; en clair : type, date, langue, statut |
| Journaux sans PII | Méthode et code de réponse uniquement (ni IP, ni corps, ni paramètres) |
| Indisponibilité mail | Demande enregistrée d'abord ; notification en file, réessais exponentiels (8 tentatives) ; le visiteur reçoit toujours sa référence |
| Notification interne | Aucune donnée personnelle (type, date, référence) |
| Traçabilité | Table `contact_audit` : réception, consultation, statut, effacement |
| Saturation / connexions lentes (V178-V179) | 32 requêtes simultanées au plus (au-delà : fermeture immédiate) ; **budget de 10 s par connexion** quoi que fasse le client ; côté Caddy de la vitrine : `read_header 5s`, `read_body 10s` et corps entièrement lu avant transmission (`request_buffers 8KB`) ; erreurs journalisées sans adresse IP |
| Clé Resend (V178) | Aucune redirection suivie : la clé n'est jamais renvoyée vers une autre adresse |
| Conservation / effacement | `--purge [--apply]` (`DSIG_CONTACT_RETENTION_DAYS`, défaut 1095, à valider), `--erase ID` |

## Exploitation (dans le conteneur, sans exposition réseau)

```bash
python contact_service.py --list                    # sans donnée personnelle
python contact_service.py --show ID                 # déchiffré, consultation tracée
python contact_service.py --set-status ID REPONDUE  # NOUVELLE | EN_COURS | REPONDUE | CLOSE
python contact_service.py --erase ID
python contact_service.py --purge [--apply]
python contact_service.py --notify < config.json    # {"api_key","sender","recipients":[...]} (max 5)
```

## Mise en service (plus tard, avec approbation explicite)

1. Générer la clé Fernet hors Git ; la **sauvegarder séparément** de la base (sans elle, les demandes sont illisibles).
2. Fichier d'environnement privé (mode 0600) : `DSIG_CONTACT_KEY`, `DSIG_CONTACT_ORIGIN=https://dsig-consulting.com`, `DSIG_TRUSTED_HOPS=2`, `DSIG_CONTACT_ENABLED=0`.
3. Construire l'image depuis le SHA approuvé, puis `docker compose -f compose.contact.yaml up -d` (réseau `edge`, alias `dsig-contact`).
4. Étape 2 (PR suivante) : vitrine construite avec le formulaire activé — impossible tant que `node scripts/legal-content.mjs` signale des champs manquants.
5. Après preuve d'un envoi et d'une notification réels : `DSIG_CONTACT_ENABLED=1`.
6. Planifier `--notify` (toutes les 2 min) et `--purge --apply` (mensuel), sauvegarde chiffrée du volume.

## Vérification

```bash
python -m unittest test_contact_service
```
CI : construction de l'image, absence du code REC, santé, refus 503 tant que fermé, 404 hors `/api/contact`, composition validée.
