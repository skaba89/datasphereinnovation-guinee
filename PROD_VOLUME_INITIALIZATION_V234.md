# V234-D2 — Initialisation isolée du volume

`prod_private_volume_init.initialize_isolated` réutilise le schéma métier de `server.connect(path)` sous verrou consultatif exclusif sur le répertoire. Il prépare une base temporaire sur le même système de fichiers, contrôle son intégrité et la publie par lien sans écraser une destination existante. Une base existante reconnue est laissée intacte; aucune migration de cette base n'est effectuée.

L'appelant de confiance doit établir la provenance du volume, garantir son exclusivité vis-à-vis de tous les autres processus et empêcher le remplacement du chemin. Le verrou est consultatif et ne protège pas contre les écrivains qui ne le respectent pas. Une interruption brutale peut laisser un répertoire de préparation ou un lien résiduel; arrêter et examiner l'état avant toute récupération, sans effacer automatiquement les données. Aucun point d'entrée CLI ni autorisation runtime n'est ajouté. Les verrous PROD restent actifs.

Tests : `python -m unittest test_prod_private_volume_init test_prod_private_data_lifecycle` sous un utilisateur Linux non-root. Rollback : revert du code; conserver les volumes et les preuves. La qualification sur le VPS, les migrations persistantes et l'intégration de l'autorisation restent obligatoires.
