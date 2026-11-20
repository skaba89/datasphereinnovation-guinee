# V45 — Dossier de lancement et preuves techniques

Sur le VPS, exécuter `python3 scripts/release-evidence.py`. Le rapport contrôle les deux projets actifs, leurs volumes distincts, leurs ports loopback, l'absence du réseau edge côté candidat, les contrôles preflight et antivirus. Il ne lit ni n'affiche les valeurs d'environnement. Il ne modifie aucun service et ne publie rien. Les tests EICAR sont des contenus fictifs envoyés au scanner privé.

PASS signifie que ces contrôles techniques sont satisfaits ; le script ne valide ni la version exacte de l'image déployée ni les gates manuelles. Conserver le rapport et la référence du commit et des images déployées. Compléter les preuves V39 et les 20 scénarios V38 ; confirmer l'externalisation et restauration, l'alerte externe réellement reçue, la revue de sécurité et l'autorisation humaine. Le verrou PROD reste actif.

Après validation complète, soumettre une version dédiée à la publication : revue des protections HTTP, limitation de débit par IP réelle, identité de l'entreprise et mentions légales validées, séparation des espaces publics et privés. Aucun changement DNS, proxy ou données réelles dans cette PR.
