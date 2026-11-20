# Audit interne V25 — 20 novembre 2026

Périmètre : branche main après PR 20, serveur Python, authentification, autorisations, données SQLite, documents, frontend et CI. Audit de code interne, pas un pentest indépendant ni une certification. Environnements DEV/REC uniquement.

| Constat | Risque | Traitement / preuve |
|---|---|---|
| Serveur HTTP multi-thread sans plafond | Élevé : saturation | 32 handlers maximum, délai socket 10 s ; contrôle complémentaire au reverse proxy requis |
| Cadrage HTTP ambigu | Élevé : désynchronisation | Rejet Transfer-Encoding et Content-Length multiple ou invalide, tests HTTP bruts |
| Service statique générique | Élevé : exposition accidentelle | Extension et nom autorisés, liens symboliques refusés, tests traversée et HEAD API |
| Origine non contrôlée uniformément sur certaines lectures | Moyen | Vérification commune admin avant autorisation, test origine étrangère |
| Limiteur d'authentification global unique | Moyen : déni de service ciblant tous les comptes | 10 tentatives par IP et 120 globales / minute, sans confiance dans X-Forwarded-For ; proxy à configurer |
| Table de limitation publique non bornée | Moyen : croissance mémoire | Nettoyage des entrées expirées et plafond 2048 IP |
| Journal HTTP avec chemin et paramètres | Moyen : divulgation | Journal méthode/statut/taille sans URI ni paramètres |
| MFA, RBAC et sessions | Contrôles existants | Tests de matrice, activation, rejeu TOTP, révocation et expiration ; bootstrap réservé à la recette |
| GED chiffrée et analyse antivirus | Contrôles existants | Tests versions, rotation, rollback, refus antivirus simulé ; daemon réel non validé |
| Dépendances et image | Non évalué intégralement | Scan de dépendances et image avec base de vulnérabilités à jour requis avant prod |
| Sauvegarde / restauration | Contrôles de recette | Exercices isolés automatisés ; reprise VPS et sauvegarde hors site à vérifier |

## Conditions de mise en production (NO-GO actuel)

- TLS, cookies Secure, contrôle d'origine HTTPS explicite, reverse proxy et limitation par IP réelle ; aucun accès direct au serveur Python.
- Supprimer le bootstrap de recette et établir une procédure d'administration d'urgence contrôlée.
- Vérifier ClamAV réel, signatures à jour, fichiers non inspectables et test de détection inoffensif.
- Scanner les dépendances et l'image, remédier aux vulnérabilités vérifiées ; audit indépendant et tests de charge.
- Établir rétention et confidentialité des données, clés séparées et restauration réellement exercée ; supervision, alertes et journal externe.
- Recette métier avec données fictives, puis validation humaine du passage en production. Domaine cible : dsig-consulting.com, aucun DNS modifié.

Les contrôles HTTP locaux ne garantissent pas la résistance à une attaque distribuée ou au trafic lent continu. Aucun score 99/100 ni conformité réglementaire n'est revendiqué.
