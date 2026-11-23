# V171 — Espace professionnel mobile et installable

## Sur téléphone (≤ 850 px)

- Le menu des modules est replié derrière un bouton **« Menu »** (accessible au clavier, fermeture par Échap) : le contenu de la page est visible immédiatement.
- Une **barre de raccourcis** fixe en bas d'écran : Accueil, Tâches, CRM, Notifications (selon les droits du rôle), page courante mise en évidence.
- Sur ordinateur, rien ne change (menu latéral habituel, pas de barre en bas).

## Installation sur l'écran d'accueil

Depuis le navigateur du téléphone (HTTPS) : « Ajouter à l'écran d'accueil » / « Installer l'application ». L'application s'ouvre sur `connexion.html`, en plein écran, avec l'icône DSIG.

- `app.webmanifest`, icônes `icon-192.png`, `icon-512.png`, `icon-maskable-512.png`, `apple-touch-icon.png`.
- Ajouté uniquement aux pages de l'espace professionnel ; **le site public n'est pas concerné** (export statique inchangé).

## Hors connexion et confidentialité

Service worker `sw.js` :

- **jamais** de mise en cache des réponses `/api/` (données clients, devis, factures…) ;
- fichiers de l'interface : réseau d'abord (une nouvelle version est prise immédiatement), le cache ne sert que de secours hors réseau ;
- sans réseau et sans copie de la page : page `offline.html` (« Vous êtes hors connexion »).

## Serveur

La liste des fichiers statiques autorisés accepte désormais `.png` et `.webmanifest` (type `application/manifest+json`), toujours au premier niveau de `dist/` uniquement.

## Vérification

```bash
python -m unittest test_server.IntakeTests.test_installable_app_assets
python -m pytest browser_e2e.py -k mobile_shell
```
