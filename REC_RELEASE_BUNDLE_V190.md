# V190 — Préparation d'un bundle de déploiement REC

Cette étape prépare des fichiers opérationnels depuis un commit Git complet, sélectionné et approuvé par l'exploitant. Aucun changement de la branche active, des images, des volumes, des unités installées ni de PROD. Le script ne déploie rien. Ne pas utiliser le répertoire actif pour un git pull avant qualification V179 du 26 novembre.

Composants:
- b2 : trois scripts V185 indissociables.
- outbox : moteur V186, outbox V187, quatre unités optionnelles V188.
- health : diagnostic V189; bundle exige b2 et outbox ensemble.

Exemple sur worktree de qualification indépendant, avec SHA validé et CI verte:

    mkdir -m 700 ~/dsig-rec-release-staging
    python3 scripts/rec_release_bundle.py --repo . --commit <sha-complet> --private-stage-parent ~/dsig-rec-release-staging --component b2

Le payload privé contient uniquement des blobs Git explicitement autorisés et le manifeste SHA256; aucun .env, base, fichier SMTP ou clé B2. Les modes Git sont enregistrés mais les fichiers préparés restent privés 0600. Le manifeste ne prouve pas l'origine ou l'approbation du commit; contrôler ces éléments séparément. Les entrées doivent rester sous contrôle exclusif de l'opérateur. En cas d'échec d'écriture, inspecter et écarter le répertoire partiel.

## Séquencement ultérieur, après qualification V179

1. Conserver preuves et journaux du cycle V179. Ne jamais renommer les anciens marqueurs.
2. Valider la CI du commit candidat et exécuter les tests dans un worktree indépendant. Examiner les écarts et les chemins systemd.
3. Choisir une fenêtre hors sauvegarde, export, audit. Vérifier les unités actives et leurs prochaines échéances. Sauvegarder les trois scripts B2 actuels, leur empreinte et leurs modes, les unités et drop-ins pertinents. Tester le retour arrière dans un environnement distinct.
4. Après accord explicite, suspendre uniquement les timers concernés, vérifier les services inactifs et l'absence d'exécution manuelle concurrente. Installer les trois scripts B2 ensemble; vérifier empreintes et prérequis, effectuer une qualification manuelle V185, puis rétablir les timers. Le cycle V185 suivant doit être qualifié séparément.
5. Outbox: qualification indépendante d'abord en observation seule, puis SMTP de test, avant installation/activation contrôlée des unités. Ne pas désactiver les alertes historiques avant preuve de couverture. Contrôler permissions, journaux et destinataires.
6. Health: diagnostic manuel, uniquement lorsque les dépendances sont qualifiées. Un PASS local ne prouve pas la disponibilité distante.
7. Rollback B2: suspendre les timers concernés, vérifier services inactifs, restaurer ensemble les trois scripts et modes sauvegardés, vérifier les empreintes, rétablir les timers dans leur état initial. Conserver les preuves des deux versions. Rollback outbox: arrêter uniquement les nouvelles unités et préserver la base privée. Ne pas effacer les sauvegardes, ni redémarrer les autres applications.

Ce runbook ne constitue pas un installateur transactionnel ni une autorisation de production. Les étapes d'installation restent manuelles et doivent être vérifiées sur le VPS au moment de l'intervention. Tests: python3 -m unittest -v test_rec_release_bundle.
