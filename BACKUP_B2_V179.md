# V179 — Chaîne de sauvegarde REC → Backblaze B2 : export versionné, qualification manuelle

Ce document ne vaut **pas** autorisation de production. Il ne concerne que la REC.

## 1. Problème corrigé

L'audit quotidien (`scripts/audit-rec-b2.py`, #186) attend **l'archive unique créée entre 02:00 et 03:00 UTC**
et une preuve SHA256 créée **entre 03:00 et 04:00 UTC**. L'export installé sur le VPS (non versionné)
choisissait **l'archive la plus récente**. Une sauvegarde manuelle, ou un export lancé hors fenêtre,
produisait donc une preuve pour une autre archive que celle attendue : `FAIL: preuve B2 absente`.
Les contrôles de l'audit étaient justes. C'est la règle de sélection qui n'était pas partagée.

## 2. Ce qui change

| Élément | Rôle |
|---|---|
| `scripts/rec_b2.py` | **Règles uniques** partagées par l'export et l'audit : sélection de l'archive, contrôles locaux, lecture et écriture atomique des preuves, nom d'objet B2 |
| `scripts/export-rec-b2.py` | Export **versionné**. Mode obligatoire : `--scheduled` (cycle quotidien) ou `--manual [--archive NOM]` |
| `scripts/audit-rec-b2.py` | Audit quotidien inchangé dans ses contrôles, plus le mode `--manual [--archive NOM]` (qualification manuelle) |
| `deploy/systemd/dsig-rec-b2.{service,timer}` | Export planifié à 03:05 UTC, `OnFailure` vers l'alerte REC |
| `deploy/systemd/dsig-rec-backup-audit.{service,timer}` | Audit à 04:05 UTC, `OnFailure` vers l'alerte REC |

Séquencement quotidien (UTC) : sauvegarde **02:15** → export **03:05**, avec un délai maximal de 45 min, donc
une preuve toujours avant 04:00 → audit **04:05**.

### Modes

| | `--scheduled` (minuteur) | `--manual` (opérateur) |
|---|---|---|
| Archive | **exactement** celle de l'audit : unique, du jour, 02:00–03:00 UTC | la plus récente, ou `--archive NOM` (nom seul) ; au plus 24 h d'ancienneté, jamais datée dans le futur |
| Refus | avant 03:00 UTC ; zéro ou plusieurs archives dans la fenêtre | archive trop ancienne, nom invalide, lien symbolique |
| Preuve | publiée ou rafraîchie après vérification distante | publiée **seulement si absente** : ne déplace jamais la date d'une preuve quotidienne |
| Valeur | cycle quotidien (audité à 04:05) | **qualification manuelle** : ne valide jamais le cycle quotidien |

L'audit `--manual` vérifie l'archive, la preuve et l'objet distant. Il exige aussi que la preuve soit postérieure à
l'archive. Son message final est « qualification manuelle (cycle quotidien NON validé) ».

### Garanties de l'export

1. **Verrou** exclusif non bloquant `<preuves>/.export.lock` : un second export échoue aussitôt.
   Si `backup-rec.sh` est en cours (verrou `.backup.lock`), l'export refuse de démarrer, sans retenir ce verrou.
2. Contrôles locaux identiques à l'audit :
   - répertoires `0700` sans lien symbolique ;
   - archive régulière, non vide, sans droits pour le groupe ni les autres ;
   - preuve régulière en `0600` ;
   - aucun lien symbolique.
3. **Idempotence** : l'objet distant est d'abord téléchargé et haché.
   - S'il est identique, il n'y a pas de nouvel envoi.
   - S'il est absent, l'archive est envoyée puis retéléchargée et hachée.
   - S'il est **différent**, c'est un FAIL et **rien n'est écrasé**.
4. **La preuve n'est écrite qu'après la vérification distante effective.** La publication est atomique :
   fichier temporaire, `fsync`, `os.replace`, puis `fsync` du répertoire.
5. Aucun secret : la CLI `b2` utilise son propre compte autorisé (utilisateur `ubuntu`), et sa sortie est ignorée.
6. Format des preuves inchangé : `<archive>.sha256` contenant l'empreinte hexadécimale. Une ligne
   `sha256sum` existante qui nomme la même archive reste acceptée.
7. Nom d'objet : `rec/AAAA/MM/<archive>`, daté par l'archive elle-même.

## 3. Reprise après interruption

| Situation | Effet | Action |
|---|---|---|
| Coupure entre l'envoi et la preuve | Objet présent sur B2, aucune preuve | Relancer. Avant 04:00 UTC : `--scheduled`. Après : `--manual --archive <archive du jour>`. L'export trouve l'objet identique, ne le renvoie pas et publie la preuve. L'audit quotidien du jour reste FAIL : c'est le constat réel |
| Erreur réseau B2 | Aucune preuve | Même action, une fois le réseau rétabli |
| Minuteur rattrapé après un redémarrage (`Persistent=true`) | L'archive est bien externalisée, mais la preuve tombe hors fenêtre (message ATTENTION) | Aucune correction de date. L'audit du jour signale l'incident, et le cycle suivant redevient normal |
| `export B2 déjà en cours` / `sauvegarde locale en cours` | Rien n'est modifié | Attendre la fin, puis relancer |
| `objet distant différent` | Rien n'est écrasé | Incident : télécharger l'objet, comparer, faire une restauration isolée de l'archive locale. Décision humaine |
| `preuve existante incohérente` | Rien n'est écrasé | Incident : vérifier l'archive locale (`--restore-isolated`). Ne jamais réécrire une preuve à la main |
| `une archive unique attendue` | Pas d'export planifié | Vérifier la sauvegarde de 02:15 (`journalctl -u dsig-rec-backup`). Ne déplacer ni renommer aucune archive |

Interdits : modifier les dates (`touch`), créer une preuve à la main, supprimer des archives locales ou distantes.

## 4. Déploiement REC

Étape 0, en **lecture seule** : identifier ce qui est installé mais non versionné, puis envoyer la sortie avant
d'aller plus loin. `systemctl cat` est filtré : il n'affiche aucune valeur de variable d'environnement.

```bash
cd /home/ubuntu/datasphereinnovation-guinee && git fetch origin && git merge --ff-only origin/main && git log --oneline -1
systemctl list-timers 'dsig-rec-*' --all --no-pager
for u in dsig-rec-b2.service dsig-rec-b2.timer dsig-rec-backup-audit.service dsig-rec-backup-audit.timer; do
  echo "## $u"; systemctl cat "$u" 2>/dev/null | grep -E '^(#|\[|Description|ExecStart|EnvironmentFile|OnCalendar|Persistent|User|After|Wants|Requires|OnFailure|Timeout|WorkingDirectory)'
done
stat -c '%a %U %F %n' /home/ubuntu/dsig-backups /home/ubuntu/dsig-b2-automation
ls -l /home/ubuntu/dsig-b2-automation | tail -n 8
~/.local/bin/b2 version
```

Étapes 1 à 5 : à lancer après validation de l'étape 0.

```bash
# 1. Sauvegarde des unités actuelles (retour arrière)
B=/root/dsig-b2-units-$(date -u +%Y%m%dT%H%M%SZ); sudo mkdir -m 700 "$B"
for u in dsig-rec-b2.service dsig-rec-b2.timer dsig-rec-backup-audit.service dsig-rec-backup-audit.timer; do
  [ -e /etc/systemd/system/$u ] && sudo cp -a /etc/systemd/system/$u "$B"/
  [ -d /etc/systemd/system/$u.d ] && sudo cp -a /etc/systemd/system/$u.d "$B"/
done; sudo ls -la "$B"
# 2. Qualification manuelle avec le script versionné et la vraie CLI b2 (archive la plus récente)
python3 scripts/export-rec-b2.py --manual && python3 scripts/audit-rec-b2.py --manual
# 3. Installation des unités versionnées
sudo install -m 644 deploy/systemd/dsig-rec-b2.service deploy/systemd/dsig-rec-b2.timer \
  deploy/systemd/dsig-rec-backup-audit.service deploy/systemd/dsig-rec-backup-audit.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dsig-rec-b2.timer dsig-rec-backup-audit.timer
systemctl list-timers 'dsig-rec-*' --no-pager
python3 scripts/audit-rec-b2.py --preflight
# 4. Le lendemain, après 04:05 UTC : cycle quotidien réel
journalctl -u dsig-rec-backup -u dsig-rec-b2 -u dsig-rec-backup-audit --since '-1 day' --no-pager | tail -n 40
```

Critère de succès : le journal de `dsig-rec-b2` contient « PASS », celui de `dsig-rec-backup-audit` contient
« PASS : cycle quotidien REC vers B2 vérifié », et aucune alerte n'a été reçue.

## 5. Retour arrière

```bash
B=/root/dsig-b2-units-<horodatage>   # répertoire de l'étape 1
sudo systemctl disable --now dsig-rec-b2.timer dsig-rec-backup-audit.timer
for u in dsig-rec-b2.service dsig-rec-b2.timer dsig-rec-backup-audit.service dsig-rec-backup-audit.timer; do
  if sudo test -e "$B/$u"; then sudo cp -a "$B/$u" /etc/systemd/system/; else sudo rm -f /etc/systemd/system/$u; fi
done
sudo systemctl daemon-reload && sudo systemctl enable --now dsig-rec-b2.timer
systemctl list-timers 'dsig-rec-*' --no-pager
```

Le script d'export non versionné n'est ni modifié ni supprimé : les anciennes unités le retrouvent tel quel. Les
preuves écrites par V179 ont le format d'origine et restent lisibles. Aucune archive n'est supprimée.

## 6. Rapport de non-régression

- **Nouveaux tests** : `test_export_rec_b2.py`, 25 tests. B2 est simulé en mémoire, les horloges sont injectées,
  et `os.utime` est appelé uniquement dans les tests pour donner à la preuve la date qu'aurait produite l'export à
  l'heure simulée.
- **Scénarios couverts** :
  - cycle quotidien nominal (export puis audit) ;
  - qualification manuelle hors fenêtre, et audit quotidien qui reste FAIL dans ce cas ;
  - archive quotidienne manquante, ou plusieurs archives dans la fenêtre ;
  - archive manuelle plus récente que l'archive quotidienne, que le cycle n'utilise pas ;
  - preuve absente, incohérente, périmée, ou antérieure à l'archive ;
  - format `sha256sum` existant ;
  - SHA256 distant différent (non écrasé) ;
  - objet distant absent ;
  - archive vide ;
  - permissions incorrectes (archive et répertoire) ;
  - liens symboliques (archive, preuve) ;
  - erreur réseau, puis reprise ;
  - export concurrent ;
  - sauvegarde en cours ;
  - reprise après un envoi interrompu ;
  - archive trop ancienne ou datée dans le futur ;
  - export planifié avant 03:00 ;
  - rattrapage tardif signalé ;
  - CLI sans mode ;
  - séquencement systemd et absence de secret dans les unités.
- **Tests existants inchangés et verts** : `test_audit_rec_b2.py` (9), `test_export_offsite.py`.
  `backup-rec.sh` et ses unités ne sont pas modifiés.
- **Durcissement de l'audit** : les répertoires de sauvegarde et de preuves doivent être en `0700`, sans lien
  symbolique. La preuve doit contenir une empreinte valide. Ce contrôle est vérifié à l'étape 0.
