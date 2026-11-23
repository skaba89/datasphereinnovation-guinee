# V163 — Rapport hebdomadaire de direction

Un e-mail interne résume chaque lundi les 7 jours précédents (jour d'envoi exclu) :

- **Activité commerciale** : demandes reçues par type, prospects CRM créés automatiquement et rattachés, demandes qualifiées, devis transmis, opportunités gagnées et perdues.
- **Pipeline actuel** : nombre d'opportunités par étape.
- **Points d'attention** : demandes sans traitement depuis plus de 48 h, relances commerciales en retard (société et sujet, 10 au plus), créances échues non encaissées par devise.

Confidentialité : uniquement des agrégats, plus la société et le sujet des relances en retard. Ni nom de contact, ni e-mail, ni contenu de message. Indicateurs opérationnels, pas un état comptable.

## Aperçu sans envoi

```bash
python server.py --weekly-report
```

## Envoi (REC)

Fichier dédié, distinct de `/etc/dsig-rec-contact.json` (dont le format strict n'accepte pas `report_recipients`) :

```bash
sudo install -m 600 /dev/null /etc/dsig-rec-report.json   # uniquement si absent
sudoedit /etc/dsig-rec-report.json
```

```json
{"api_key":"re_REMPLACER","sender":"notifications@dsig-consulting.com","test_recipient":"REMPLACER_BOITE_DE_TEST","report_recipients":["REMPLACER_DIRECTION"]}
```

- Sans `report_recipients`, le rapport part vers `test_recipient`. 10 destinataires au plus.
- Un seul envoi accepté par semaine ISO (table `weekly_reports`, clé d'idempotence Resend). Un échec est retenté au passage suivant.
- Production bloquée : la commande refuse de s'exécuter hors DEV/REC.

Après un premier envoi manuel vérifié (`sudo cat /etc/dsig-rec-report.json | docker compose … exec -T dsig python server.py --send-weekly-report`), installer et activer `deploy/systemd/dsig-rec-weekly-report.service` et `.timer` (lundi 07:00 UTC). Ces unités ne sont pas installées automatiquement.

Tests : `python -m unittest test_weekly_report`.
