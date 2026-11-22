# V79 — Dossier de validation de la candidate DSIG

PR 77 et 78 fusionnées, CI 44898838574 et 44899008135 réussies. Ces preuves historiques ne valident pas le prochain commit ni le VPS.

Le registre complète les rapports techniques existants (scripts/release-evidence.py, V76, V77, V78). Il ne les remplace pas et ne prétend pas vérifier l'authenticité des pièces.

## Contrôles obligatoires

| Domaine | Pièce attendue |
|---|---|
| CI et isolation | Tous les jobs CI du SHA exact, rapport suite isolée |
| Infrastructure | V78, V76 du conteneur réel, accès TLS restreint |
| Vitrine | Parcours FR/EN, formulaire et mobile |
| CRM | Organisations, opportunités, catalogue privé, diagnostic Supply Chain |
| RH et missions | Recrutement, affectation, CRA, contrat, renouvellement |
| Finance | Devis, échéance, règlement, dépense, rapprochement, exports |
| Identité | Matrice neuf rôles, MFA, révocation, refus des accès non autorisés |
| GED | Contrôle antivirus réel et refus en cas d'indisponibilité |
| Continuité | Sauvegarde hors site et restauration applicative isolée, alertes reçues |
| Gouvernance | Compatibilité rollback, revue indépendante, politique de rétention, validation métier et décision humaine |

## Utilisation

Après revue du SHA approuvé, générer un nouveau formulaire privé hors Git :

```bash
umask 077
sha=$(git rev-parse HEAD)
python3 release_evidence.py "$sha" --template
```

Enregistrer la sortie dans un fichier de recette privé neuf, compléter les 25 contrôles (schéma 2, voir QUALIFICATION_FINAL_V156.md) avec PASS, FAIL ou NOT_RUN, le SHA exact, la date UTC ISO (terminée par Z), le responsable et une référence de preuve expurgée. Ne mettre ni secrets ni données personnelles dans les références. Puis :

```bash
python3 release_evidence.py "$sha" < /chemin/prive/recette.json
```

NO_GO (code 1) signifie qu'une déclaration manque, est invalide ou négative. REVIEW_REQUIRED (code 0) signifie uniquement que les déclarations sont complètes : vérifier les preuves, leur fraîcheur et les signatures séparément. Le compteur n'est pas un score de maturité. La sortie n'affiche pas les références ni les responsables. Aucun changement d'environnement, aucune écriture de données métier, aucune autorisation PROD. Nouveau SHA = nouveau dossier. La production reste bloquée par le serveur et requiert une version dédiée et une autorisation explicite.
