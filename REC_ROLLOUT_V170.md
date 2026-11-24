# V170 — Mise en recette des livraisons V162 à V169 (PR #157 à #168)

Guide opérateur pour installer sur la **REC** (`dsig-rec`, service `dsig`) les fonctionnalités CRM/ERP livrées depuis la PR #157, puis les vérifier. Il complète — sans les remplacer — les procédures **V77** (OPERATIONS.md) et **V96** (REC_UPGRADE_V96.md), qui restent la référence pour la préparation, l'activation et le retour arrière.

> Aucune étape de ce guide ne concerne la production, Caddy, les autres applications du VPS, `compose.rec-edge.yaml` ni les registres d'approbation. **NO GO PROD** inchangé. Le formulaire public reste bloqué par la validation juridique (V161).

## 1. Contenu livré

| PR | Version | Fonction | Données |
|---|---|---|---|
| #157 | — | Pipeline Kanban (glisser-déposer) | aucune nouvelle table |
| #158 | V162 | Prospect CRM créé automatiquement à chaque demande web | `request_leads` |
| #159 | — | Cockpit d'accueil (indicateurs) | — |
| #160 | — | Fiche client 360° | — |
| #161 | — | Recherche globale (Ctrl+K) | — |
| #162 | V163 | Rapport hebdomadaire de direction par e-mail | `weekly_reports` |
| #163 | V164 | Relance automatique des devis sans décision (J+7) | file `contact_mail` (`followup-…`) |
| #164 | V165 | Rappels « à facturer » et relance des factures échues (J+7, J+21) | `billing_dunning`, file `contact_mail` (`dunning-…`) |
| #165 | V166 | Rapport de direction en ligne, CSV et PDF | — |
| #166 | V167 | Tâches commerciales | `crm_tasks` |
| #167 | V168 | Modèles d'e-mails commerciaux | `email_templates` (6 modèles créés au démarrage), `crm_email_log` |
| #168 | V169 | Devis en PDF | — |

**Aucune dépendance nouvelle, aucun changement Compose ou Dockerfile.** Le schéma n'évolue que par création de tables (`CREATE TABLE IF NOT EXISTS`) : l'ancienne image reste compatible avec la base (voir § 6 pour la file d'e-mails).

## 2. Préparation (V77 / V96)

1. Choisir le SHA approuvé : le commit de fusion de `main` contenant cette page, avec les **cinq** jobs CI verts (`regression 3.10`, `regression 3.12`, `browser-acceptance`, `docker-smoke`, `public-docker-smoke`).
2. Appliquer **V96 § Avant la mise à niveau** puis `bash scripts/prepare-rec-upgrade.sh "$sha"` (V77). Conserver le rapport, les identifiants d'images et la sauvegarde chiffrée hors site.
3. Contrôler la configuration candidate avec `scripts/check-rec-upgrade.py` (V96). Seule la ligne `services.dsig.image` doit différer.

## 3. Avant l'activation : mesurer les relances en attente

La planification quotidienne (`dsig-rec-notifications.timer`, 08:00 UTC) met en file, **dès son premier passage**, toutes les relances éligibles accumulées dans la base de recette : devis transmis depuis plus de 7 jours, factures échues depuis plus de 7 jours. Avant d'activer, mesurer ce volume avec l'image candidate, sur une **copie isolée** de la base (jamais la base active) :

```bash
# Dans un conteneur jetable de l'image candidate, sur la copie restaurée par V77 :
python server.py --automation-preview
# → {"quote_followups": N, "invoice_reminders": M}   (aucune écriture, transaction annulée)
```

En recette, ces e-mails partent uniquement vers `test_recipient` ou les adresses listées dans `rec_customer_recipients` (`/etc/dsig-rec-contact.json`). **Vérifier que cette liste ne contient que des adresses de test** avant l'activation. Si `N + M` est élevé, c'est attendu sur une base de recette ancienne ; décider en connaissance de cause (la boîte de test recevra ce volume).

## 4. Activation

Suivre **V77 § Activation manuelle après validation humaine** (overlay image minimal hors Git, `up -d --no-build --pull never --wait dsig`). Puis rejouer V76 (version exécutée), preflight et monitor.

## 5. Configuration après activation

### 5.1 Rapport hebdomadaire (V163)

1. Créer `/etc/dsig-rec-report.json` (propriétaire `root`, groupe `ubuntu`, mode `0640`) — fichier **distinct** de `/etc/dsig-rec-contact.json` :

   ```json
   {"api_key": "re_…", "sender": "rapport@dsig-consulting.com", "test_recipient": "boite-test@…",
    "report_recipients": ["direction@…"]}
   ```

   `report_recipients` est facultatif (10 adresses maximum ; à défaut, `test_recipient`).
2. Aperçu sans envoi : `docker compose -p dsig-rec -f … exec -T dsig python server.py --weekly-report`.
3. Envoi manuel unique, puis vérification de la réception : `… exec -T dsig python server.py --send-weekly-report < /etc/dsig-rec-report.json` → `SENT` (un second appel la même semaine répond `ALREADY_SENT`).
4. Seulement ensuite, installer le minuteur (lundi 07:00 UTC) :

   ```bash
   sudo systemd-analyze verify deploy/systemd/dsig-rec-weekly-report.{service,timer}
   sudo install -m 644 deploy/systemd/dsig-rec-weekly-report.{service,timer} /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now dsig-rec-weekly-report.timer
   systemctl list-timers 'dsig-rec-*' --all
   ```

### 5.2 Relances automatiques (V164, V165) et rappels internes (V165, V167)

Rien à installer : elles utilisent les minuteurs existants `dsig-rec-notifications` (planification) et `dsig-rec-contact` (envoi). Contrôler après le premier passage :

```bash
sudo journalctl -u dsig-rec-notifications.service -n 20 --no-pager
# « N relance(s) de devis planifiée(s). » / « M relance(s) de facture planifiée(s). »
docker compose -p dsig-rec -f … exec -T dsig python server.py --contact-mail-status
```

## 6. Retour arrière

Appliquer **V77 § Retour arrière**. Le schéma étant purement additif, l'ancienne image démarre sur la base modifiée. **Précaution spécifique** : l'ancienne version ne connaît pas les e-mails `followup-…` et `dunning-…` ; s'il en reste en attente, elle les enverrait à la boîte de test sous la forme d'un accusé de réception générique. Avant de relancer l'ancienne image, les neutraliser (base fermée aux écritures, sauvegarde vérifiée) :

```sql
UPDATE contact_mail SET state='FAILED' WHERE state='PENDING' AND (kind LIKE 'followup-%' OR kind LIKE 'dunning-%');
```

Puis `sudo systemctl disable --now dsig-rec-weekly-report.timer` si le rapport avait été activé. Ne supprimer aucune table ni aucun volume.

## 7. Recette fonctionnelle (données fictives uniquement)

### 7.0 Recette automatisée (V177)

Sur le VPS, depuis le dépôt à jour (le jeton est lu dans le conteneur et n'est jamais affiché) :

```bash
cd /home/ubuntu/datasphereinnovation-guinee && git fetch origin && git merge --ff-only origin/main
DSIG_ADMIN_TOKEN="$(docker exec dsig-rec-dsig-1 printenv DSIG_ADMIN_TOKEN)" python3 scripts/acceptance-rec.py
```

Le script déroule, avec des données fictives marquées `RECETTE-AUTO` : formulaire → demande + prospect CRM (téléphone, type Formation), recherche globale, tâche (création, report, clôture, verrou), devis → PDF sans coût interne, rapport hebdomadaire JSON/CSV, e-mail commercial (aperçu + historique), refus des API sans authentification, puis **droit à l'effacement** sur la demande fictive. Sortie JSON PASS/FAIL par étape, code retour 0 seulement si tout passe. Il refuse toute autre cible que la REC. Restent manuels : le téléphone (menu, barre, écran d'accueil) et la connexion MFA d'un compte DIRECTION.

Cocher chaque ligne et conserver les preuves expurgées (captures sans données personnelles réelles).

| # | Scénario | Résultat attendu |
|---|---|---|
| 1 | Envoyer une demande web fictive | Prospect créé automatiquement dans le CRM, attribué au commercial le moins chargé, échéance 48 h |
| 2 | Renvoyer une demande avec le même e-mail | Rattachée au prospect existant (pas de doublon) |
| 3 | Kanban : déplacer une carte | Statut mis à jour ; conflit signalé si modifiée ailleurs |
| 4 | Accueil (`connexion.html`) | Cockpit : indicateurs cohérents avec le CRM |
| 5 | Ctrl+K « energie » | Trouve « Énergie… » (accents ignorés), résultats limités aux droits du rôle |
| 6 | Fiche client depuis le Kanban | Opportunités, demandes, devis, factures selon le rôle ; chronologie |
| 7 | Kanban « + Tâche » → créer, « Demain », « Fait » | Tâche classée Aujourd'hui → À venir → Terminées ; retard visible dans Notifications le lendemain |
| 8 | Fiche client « Écrire au client » (modèle Relance) | Aperçu rempli, enregistrement dans l'historique, ouverture de la messagerie |
| 9 | Modèles d'e-mails (ADMIN) : saisir `{nom}` | Refusé ; `{contact}` accepté |
| 10 | Devis : « Télécharger le PDF » et « PDF anglais » | PDF lisible, total correct, **ni coût ni marge**, filigrane « RECETTE » |
| 11 | Pilotage → « Rapport hebdomadaire (CSV / PDF) » | Indicateurs, semaine précédente, export CSV, impression PDF |
| 12 | Devis transmis il y a > 7 jours (date fictive) | Après le minuteur : une relance dans la boîte de test, note dans l'historique de la demande |
| 13 | Facture fictive échue > 7 jours | Une relance (référence + échéance, sans montant) ; aucune si relance manuelle < 7 jours |
| 14 | Jalon validé non facturé / échéance à facturer | Notifications « Jalon validé à facturer » / « Échéance à facturer » |
| 15 | Rôles : COMMERCIAL, DIRECTION (MFA), RH | Menus et accès conformes ; DIRECTION en lecture seule sur tâches et e-mails ; RH sans CRM |
| 16 | Mobile (360 px) sur Tâches, Fiche client, Rapport | Aucun défilement horizontal |

## 8. Hors périmètre

- Production, formulaire public, envoi d'e-mails commerciaux depuis la plateforme : bloqués jusqu'à validation juridique (V161) et approbation humaine.
- Les PDF de devis portent « document non contractuel » tant que l'identité légale de l'émetteur n'est pas validée.
