# V87 — Bilan de recette et préparation de mise en service

Date : 21 novembre 2026. Périmètre : DSIG, données fictives exclusivement.

## Preuves CI acquises

La PR [86](https://github.com/skaba89/datasphereinnovation-guinee/pull/86) est fusionnée dans main au commit `630173146704422620a5f1bffa10aad87bfccfce`. Son commit de tête `8c5daae919c095095f86ae76a3b889b2accb3dc6` a passé les quatre jobs du [run 44906116880](https://github.com/skaba89/datasphereinnovation-guinee/actions/runs/44906116880) : Python 3.10, Python 3.12, browser-acceptance et docker-smoke. Cette preuve ne certifie pas un déploiement et ne s'applique pas automatiquement à un SHA ultérieur.

Les 15 scénarios de browser_e2e.py de V86 couvrent :

| Domaine | Scénarios automatisés (CI V86) | Recette sur VPS |
|---|---|---|
| Vitrine | public_intake_and_catalogue, english_parity_and_intake, mobile_navigation_and_accessibility, self_hosted_typography, cybersecurity_expertise_and_prefill, logistics_expertise_bilingual | NOT_RUN |
| Identité et autorisations | admin_mfa_all_modules_and_logout, consultant_scope, non_admin_role_navigation_and_api_matrix, anonymous_private_routes_and_crm_workspace | NOT_RUN |
| Régie | browser_prospect_to_paid_contract | NOT_RUN |
| Forfait et contrôle financier | fixed_price_milestones_and_budget_reconciliation | NOT_RUN |
| Renouvellements | contract_renewal_alerts_and_notifications | NOT_RUN |
| RH et GED | recruitment_consultant_and_private_document_lifecycle | NOT_RUN |
| Avant-vente | tender_pipeline_and_appointment_conflicts | NOT_RUN |

NOT_RUN signifie absence de preuve terrain dans ce dossier, pas absence certaine de déploiement. Scanner sain simulé en CI ; validation réelle ClamAV obligatoire.

## Exécution ordonnée sur REC

Se référer à OPERATIONS.md V75–V77 et aux procédures existantes. Ne pas exposer la candidate ni modifier les autres applications du VPS.

1. Identifier le SHA approuvé et vérifier les quatre jobs CI correspondants ; inventorier le conteneur, le mode REC, les volumes et overlays sans afficher les secrets.
2. Préparer la mise à niveau avec scripts/prepare-rec-upgrade.sh selon V77 : image candidate, tests isolés, sauvegarde et restauration de vérification. Ne pas activer sans revue humaine.
3. Après activation REC contrôlée, vérifier le SHA effectivement exécuté via scripts/verify-rec-release.py ; contrôler health/ready et preflight.
4. Vérifier TLS et accès REC autorisé/refusé, comptes nominatifs, MFA réelle et permissions, notamment après révocation.
5. Rejouer les parcours métier ci-dessus avec des données fictives. Pour chaque scénario noter rôle, préconditions, résultat attendu, résultat réel, preuve expurgée et anomalie éventuelle.
6. Vérifier ClamAV réel avec check_antivirus.py (contenu sain et EICAR inoffensif), refus en cas d'indisponibilité dans un environnement isolé.
7. Tester la sauvegarde hors site et la restauration applicative isolée, clés séparées ; mesurer RPO/RTO observés et vérifier la réception d'une alerte de supervision approuvée.
8. Si une candidate PROD isolée existe, exécuter scripts/release-evidence.py conformément à sa procédure. Un PASS technique n'autorise jamais PROD.
9. Renseigner les dix contrôles G01–G10 du dossier de preuve existant, sur le SHA exact. Exécuter scripts/release-gates.py avec le fichier de preuves privé hors Git. Chaque contrôle exige PASS, preuve et reviewer ; ne pas renseigner de valeurs fictives.

## Décision

**NO GO PROD à ce stade** : preuves terrain non fournies dans ce dossier ; validation métier, sécurité indépendante, mentions légales/rétention, capacité infrastructure, sauvegarde externe restaurée et autorisation humaine à établir. La CI ne couvre pas ces engagements.

Ne jamais versionner de données personnelles, clés, exports, sauvegardes ou journaux contenant des secrets. Aucun passage automatique en production, aucun changement DNS ni déploiement dans V87.
