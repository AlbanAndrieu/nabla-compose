# Cutover Catalog v2 : FastAPI, Site Alban, observabilité, TrueNAS

## Contrat actuel vérifié

`nabla-compose` publie `catalog/generated/entities.json` et
`catalog/generated/identity-map.json` avec le **même** `catalogRevision`.
Le crosswalk est **généré** depuis les références Compose
`com.albandrieu.nabla.entity-ref` et les identifiants Gatus, avec
`sourceType`, `sourceId`, `entityRef` et `evidence` (provenance
déclarative). Aucun second mapping maintenu à la main.

Dernier snapshot contrôlé : 143 applications Homarr, 85 sondes Gatus,
85 moniteurs AutoKuma, 225 mappings (140 Compose / 85 Gatus),
aucune référence non résolue. **Ces nombres décrivent les artefacts Git,
pas l'état d'exécution sur TrueNAS.**

`fastapi-sample` consomme le graphe Backstage vérifié et expose au site
`GET /api/site/catalog/v2`, en-tête serveur `X-Diagnostics-Key` ;
réponse `schemaVersion=2`, `model=backstage`,
`catalogRevision`, `entities[]` expurgées. Site Alban possède déjà
`lib/homelabSiteCatalog.ts` et `lib/homelabServicesServer.ts` :
ils lisent **ce** endpoint, pas `/api/homelab-services`.

## Cas de la clé de test volontairement invalide

`DIAGNOSTICS_ACCESS_KEY=1234` est un **fixture négatif Vercel** :
401/403 de FastAPI → `access-denied` ; aucune tentative de clé alternative,
aucune exposition du secret au navigateur, aucun fallback v1, pas de faux état
applicatif DOWN. Le routeur privé Next.js répond par un état non disponible
neutre, avec la barrière d'accès propriétaire séparée.

La vraie clé n'est pas écrite dans Git et ne doit pas être demandée dans une PR.
Ne pas modifier `HOMELAB_TRUSTED_CIDRS` pour y ajouter les IP de sortie Vercel :
la clé SERVICE et l'autorisation OWNER sont deux contrôles différents.

## Phases d'exploitation : deux vagues

Le script `scripts/truenas/plan-catalog-v2-restart.py` prépare des vagues
avec un snapshot privé `app.query`. Il **ne redémarre rien**.

- **Vague 1 : RUNNING** — inventorier ce qui fonctionne actuellement, traiter
  ces applications prioritairement après analyse des dépendances v2 ;
  ne pas arrêter les services déjà sains pour faire une démonstration.
- **Vague 2 : autres états** — STOPPED, CRASHED, UNKNOWN ; distinguer
  `planned`/`disabled` avant d'autoriser un démarrage.
- Pour les deux vagues, vérifier le manifeste Vaultwarden, la matérialisation
  des fichiers runtime (0600), et l'authentification applicative réelle **sans
  imprimer de secret**. `vaultwardenItemVerified=false` signifie que le
  script n'a pas vérifié l'item réel. Aucune promesse de disponibilité
  ne découle de la simple présence d'un fichier.
- Les dépendances Backstage `spec.dependsOn` s'ajoutent aux dépendances
  locales `depends_on` Compose, et ne doivent pas être copiées en `x-nabla`.

## Acceptation à maintenir

- Les projections JSON sont reproductibles (`--check`).
- Les IDs de corrélation sont uniques, audités avec provenance, sans
  correspondance inférée uniquement depuis un nom ou une adresse IP.
- La logique de santé distingue `unknown`/`access-denied`/`probe failed`
  de `DOWN` confirmé.
- Les scripts TrueNAS/clients FastAPI et site qui lisent encore les données
  v1 sont à retirer via leurs migrations respectives, sans garantie de
  disponibilité permanente pendant le cutover.
