# Bitwarden CLI / Vaultwarden — matrice de compatibilité opérateur

État au **13 octobre 2026**. Le fichier `scripts/truenas/diagnose-vaultwarden-cli.sh`
sert aussi sur la workstation : il est **lecture seule**, ne lance ni
`bw login`, ni `bw unlock`, ni `bw sync` et ne lit pas les valeurs du coffre.

| CLI | Vaultwarden | Preuve / verdict |
| --- | --- | --- |
| `2026.8.0` | Instance personnelle (version serveur non fournie) | **Accepté sur workstation le 13/10/2026** : `bw unlock` et `bw sync` ont réussi |
| `2026.9.0` | Même instance personnelle | **Bloqué** : `KeyIdBackfillError`, POST de migration cryptographique renvoyant HTTP 404 |
| Autres versions | Toute version | **Non vérifié** : ne pas inférer la compatibilité depuis `bw --version` seul |

Le diagnostic classe les versions par expérience **sur cette instance**, et
non comme une matrice universelle. Vérifier séparément la version
Vaultwarden via les métadonnées de l'application, sans afficher les tokens.
Le CLI Node 2026.8.0 déclare `node ~22` et `npm ~10` : sur cette
workstation `node 24.18.1` et `npm 12.2.0` ont produit `EBADENGINE`
mais le déverrouillage et le sync ont fonctionné. Le fonctionnement observé
ne transforme pas ces versions Node/npm en combinaison officiellement supportée.

## Vérification workstation, sans secrets

```bash
type -a bw
bw --version
bw config server
bash scripts/truenas/diagnose-vaultwarden-cli.sh
```

Pour conserver un état compatible avec les déclarations d'engine, utiliser
Node 22/npm 10 dans un **contexte isolé** si nécessaire, sans remplacer
automatiquement le runtime Node utilisé par les autres outils.
Si `bw` provient de npm global, l'installation explicitement testée est :

```bash
npm install -g @bitwarden/cli@2026.8.0 --save-exact
hash -r
bw --version
```

**Ne pas** exposer `BW_SESSION` dans des logs, ni recopier des résultats
`bw list items`. La session CLI active reste chiffrée côté Vaultwarden
et ne doit pas servir de secret applicatif. Le passage à une version de
CLI plus récente nécessite la confirmation de l'API key-id côté Vaultwarden
et un test de login/unlock/sync volontaire après sauvegarde.

La séquence d'initialisation de `nabla/env/home/dev.env.sh` charge
`env/home/pass/pass.env.sh` lorsque l'endpoint `/api/config` répond ;
la disponibilité HTTP n'est **pas** une preuve de compatibilité crypto.
Pour éviter de bloquer le shell pendant une intervention,
`NABLA_SECRETS_MODE=off` désactive le chargement du fichier privé.
Ce n'est pas une révocation de session ni une correction d'API.
