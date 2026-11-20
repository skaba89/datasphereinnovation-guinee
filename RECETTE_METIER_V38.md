# V38 — Recette métier DSIG (REC uniquement)

## Conditions
- Version déployée et CI verte ; noter commit, date UTC et testeur.
- Utiliser exclusivement des comptes et données fictifs préfixés REC-V38. Ne jamais publier une clé, un mot de passe, un code MFA, un document client ou un export nominatif.
- Tester sur la recette HTTPS autorisée. Ne pas désactiver les protections, ni supprimer les comptes/données existants.
- Pour les opérations financières, utiliser une devise unique par scénario ; ne pas interpréter le registre comme une comptabilité légale.
- Chaque test reçoit PASS, FAIL, BLOCKED ou NOT_RUN. Aucun PASS sans résultat observé. Conserver preuves expurgées hors Git ; tout FAIL/BLOCKED critique empêche le GO.

## Parcours et critères
| ID | Domaine / rôle | Manipulation | Résultat attendu |
|---|---|---|---|
| R01 | Vitrine | Parcourir accueil, expertises, offres, carrières, anglais et mobile | Aucun lien cassé ; texte lisible |
| R02 | Prospect / COMMERCIAL | Soumettre une demande fictive depuis la vitrine, la qualifier | Demande visible uniquement au rôle autorisé, historique conservé |
| R03 | COMMERCIAL | Créer organisation CLIENT, opportunité liée, devis | Liens persistants ; doublon organisation refusé |
| R04 | COMMERCIAL | Créer appel d'offres, changer statut, saisir échéance | Historique et filtres corrects |
| R05 | RH | Créer consultant fictif puis modifier disponibilité | Profil et version persistants ; pas de droit écriture CRM |
| R06 | COMMERCIAL / ADMIN | Établir devis et le faire accepter selon workflow | Devis accepté unique, montant et devise cohérents |
| R07 | PROJET | Créer mission depuis devis accepté, affecter consultant | Chevauchement et doublon mission refusés |
| R08 | CONSULTANT / PROJET | Soumettre CRA, faire valider, tester un autre compte consultant | Seules données propres visibles ; validation interdite au consultant |
| R09 | PROJET / ADMIN | Soumettre prolongation et faire valider par administrateur distinct | Échéance mise à jour après contrôle disponibilité |
| R10 | COMPTABLE | Créance à partir CRA validés, paiement partiel puis solde | Dépassement refusé, cohérence soldes et devise |
| R11 | COMPTABLE | Enregistrer décaissement, tester référence dupliquée | Flux enregistré, doublon refusé |
| R12 | DIRECTION / CONTROLE | Lire pilotage, comparer coûts, recettes, écarts et CSV | Totaux cohérents avec données saisies, lecture seule |
| R13 | ADMIN | Déposer un fichier fictif sain, récupérer et consulter historique | Scan réussi, accès non autorisé refusé |
| R14 | DIRECTION / ADMIN | Consulter alertes et notifications | Échéances/retards plausibles ; état lecture correct |
| R15 | ADMIN / AUDITEUR | Consulter journal des accès | Autorisations et refus tracés, auditeur lecture seule |
| R16 | Tous | Vérifier connexion, déconnexion, refus des routes hors rôle | Autorisations côté serveur ; session révoquée |
| R17 | ADMIN / DIRECTION / CONTROLE / COMPTABLE / AUDITEUR | Vérifier MFA avant accès métier, puis connexion valide | Sans MFA aucun droit métier ; MFA valide ouvre uniquement les droits du rôle |
| R18 | Opérations | Exécuter preflight, test antivirus, backup V35, monitor V37 | PASS, archive hôte vérifiée, aucun impact autre application |
| R19 | Réseau | Accès HTTPS depuis IP autorisée puis autre réseau non autorisé | Certificat valide, accès non autorisé refusé |
| R20 | Opérations | Tester instance restaurée isolée avec données fictives | Connexion après révocation, parcours et totaux cohérents, base active inchangée |

Sur une mission régie fictive, exemple de rapprochement : 2 jours validés à 100 000 GNF de TJM, coût journalier 60 000 GNF, sans frais, recette facturable 200 000 GNF et coût direct 120 000 GNF ; créance 200 000 GNF et paiement 80 000 GNF donnent un solde de 120 000 GNF. Ne pas confondre recette facturable et encaissement.

## Preuves automatisées
La CI existante exécute python unittest, contrôles JS, navigateur Playwright et Docker. Les tests navigateur couvrent notamment vitrine, navigation mobile, MFA admin, accès aux 13 modules, CRM et portée consultant. Les tests serveur couvrent les cycles métier, permissions, sécurité et sauvegarde. Ces preuves locales ne remplacent pas les scénarios réels R01–R20 sur le VPS.

## Fiche de résultat (copier hors Git)
Version : ___ ; commit : ___ ; date UTC : ___ ; testeur : ___.
Pour chaque ID : statut, résultat observé, preuve expurgée, anomalie, priorité, décision et re-test.
Décision finale : NO GO tant qu'un contrôle critique reste non validé. La recette ne lève pas le verrou PROD du serveur.
