# V39 — Dossier de préparation production DSIG

**NO GO par défaut.** Le serveur refuse toujours PROD. Ce dossier ne crée aucun environnement, ne publie aucun DNS, ne modifie aucun proxy et ne constitue pas une autorisation de lancement.

## Architecture cible
- REC existante : dsig-rec, port hôte 8300 sur loopback, volume dsig-rec_dsig-data, domaine rec.dsig-consulting.com restreint au réseau autorisé.
- PROD future : projet Compose dsig-prod distinct, volume neuf et séparé, fichier de secrets dédié hors Git, port loopback distinct à réserver après inventaire, domaine dsig-consulting.com. Ne jamais réutiliser le volume REC ni les clés REC. Le reverse proxy Caddy partagé ne doit être modifié que par une configuration validée, avec sauvegarde et rollback.
- Avant exposition : revue des routes publiques/privées, limitation des abus par IP client réelle sans confiance aveugle aux en-têtes, MFA, droits, politique cookies, HTTPS, stockage chiffré au repos, antivirus privé.
- Ne pas recopier les données fictives REC en PROD ; créer les comptes initiaux selon une procédure nominative et approuvée. Inventorier les exigences légales, fiscales et de confidentialité avant données réelles.

## Gates préalables
| ID | Preuve attendue |
|---|---|
| G01 | Commit candidat identifié, CI Python 3.10/3.12, navigateur, Docker réussis |
| G02 | V38 R01-R20 exécutés avec preuves et écarts critiques résolus |
| G03 | MFA et séparation de rôles sur HTTPS, accès réseau autorisé/refusé |
| G04 | Sauvegarde quotidienne planifiée, archive vérifiée et copie chiffrée hors VPS ; clés séparées |
| G05 | Restauration isolée applicative chronométrée, objectifs RPO/RTO acceptés |
| G06 | Monitoring local planifié + supervision externe et alerte reçue par responsable |
| G07 | Ressources VPS, marge disque/RAM, test charge et absence d’impact autres services |
| G08 | Revue sécurité indépendante, gestion des secrets, données au repos et mises à jour |
| G09 | Procédure incident/rollback testée, responsable d’exploitation désigné |
| G10 | Validation humaine explicite de la release PROD et obligations métier/légales |
 
Le contrôle automatique `scripts/release-gates.py` valide uniquement la complétude déclarative et le format des preuves. Il n’atteste pas leur authenticité et ne lève jamais le verrou serveur. Conserver les références expurgées hors Git.

## Plan de bascule après autorisation explicite
1. Réserver le port et confirmer les ressources ; sauvegarder la configuration Caddy et relever les services existants.
2. Préparer une release dédiée qui traite les écarts de sécurité et lève le verrou PROD après revue ; ne pas réutiliser une image REC par simple changement de variable.
3. Démarrer PROD isolée, sans publication externe ; valider intégrité, santé, antivirus, MFA, droits et sauvegarde.
4. Valider la configuration proxy puis appliquer uniquement la route DSIG. Vérifier TLS, accès, API et non-régression des autres domaines.
5. En cas d’écart, retirer uniquement la route DSIG et remettre la configuration validée précédente ; conserver les données et preuves. Ne jamais utiliser down -v ni restaurer une archive sur la base active sans procédure approuvée.

Aucune commande de production n’est fournie tant que les gates ne sont pas validées.

Copier `release-gates.example.json` hors Git vers un fichier privé, renseigner les preuves réelles et exécuter `python3 scripts/release-gates.py /chemin/prive/gates.json`.
