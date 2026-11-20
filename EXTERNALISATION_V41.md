# V41 — Externalisation des archives REC

Le script exporte uniquement les archives chiffrées DSIG depuis le dossier privé local. Il refuse un répertoire non monté, un même système de fichiers et une destination non privée. Il compare SHA256 et publie atomiquement sans écraser. La destination doit supporter les liens physiques. Aucune clé, base en clair, suppression ou configuration réseau.

Choisir un stockage réellement hors VPS (autre serveur ou stockage distant monté) et configurer le montage et les droits avec l'administrateur. Un autre disque sur le même VPS ne garantit pas une reprise hors site. Le script ne configure ni fournisseur ni identifiants.

Après vérification du montage et création d'un dossier `dsig-rec` de mode 0700 sur celui-ci, lancer sous ubuntu :

```bash
python3 scripts/export-offsite.py /chemin/du/montage
```

Vérifier que le stockage est physiquement indépendant et que le résultat est PASS, puis planifier le transfert après sauvegarde. Conserver les clés séparément dans un coffre. Tester une restauration depuis la copie distante sans écraser la base active. Aucun GO PROD ni export automatique par défaut.
