# V184 — Registre de qualification PRA REC

Objectif : consolider des preuves réelles, sans confondre CI, préparation et reprise complète. Copier pra-qualification.example.json dans un espace privé hors Git, renseigner le commit qualifié et joindre les rapports d'exercice (sans secrets). Chaque gate PASS doit avoir un relecteur identifié, un fichier local et son SHA256. Utiliser des fichiers simples dans un répertoire privé stable, sans modifications concurrentes. Aucun PASS par défaut.

Preuves attendues : trois kits GPG vérifiés; coffre indépendant rouvert et clés testées; hôte de secours distinct; instant de cohérence du snapshot établi; image et SQLite restaurées avec santé API; systemd/ClamAV installés et testés; Caddy et HTTPS sur domaine de test; recette métier incluant connexion/MFA, documents, CRM, devis, missions, factures et droits; absence d'envoi réel; cycle automatique B2 qualifié; retour arrière exercé. V181-V183 seuls ne suffisent pas à valider ces gates.

Timing : snapshot_consistency_utc = instant de cohérence réellement démontré (pas seulement nom d'archive); exercise_start_utc = début de la simulation de perte, avant récupération des ressources; business_recovery_utc = fin de recette métier sur le service restauré. Format UTC YYYY-MM-DDTHH:MM:SSZ. Objectifs REC proposés à faire approuver : RPO 24 h, RTO 4 h. Les durées V181 ne constituent pas un RTO complet.

    python3 scripts/pra_qualification.py /private/register.json --evidence-dir /private/evidence

NO_GO signifie preuves manquantes ou objectifs dépassés. REVIEW_REQUIRED signifie uniquement complétude structurelle et empreintes conformes; un responsable doit vérifier le contenu, la provenance et la cohérence des rapports et des dates. Les attestations ne sont ni signées ni authentifiées par cet outil; les hashes ne prouvent pas leur vérité. Aucun GO automatique, aucune autorisation PROD. Les gates de release existantes restent indépendantes.

Tests : python3 -m unittest -v test_pra_qualification. Aucun changement de services ni du cycle B2.
