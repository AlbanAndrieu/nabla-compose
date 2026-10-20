# Redémarrage et recette TrueNAS sur Catalog v2

**Préparation déclarative, sans mutation du runtime.** Ce plan remplace
progressivement la lecture des `services.json`/`service-topology.json` v1
pour les nouvelles vagues de redémarrage. Ne pas exécuter le vieux
`restore-app-set.sh` comme moteur de redéploiement v2 : il ignore les
applications déjà `RUNNING` et lit encore le catalogue historique.

## 1. Avant tout changement

- Vérifier que la révision de `nabla-compose` sur TrueNAS est celle de la PR
  v2 acceptée et que `python scripts/generate-catalog-v2-artifacts.py --check`
  et `python scripts/generate-service-consumers.py --check` passent.
- Le GitOps déclaratif reste l'autorité ; pas de correction runtime non
  documentée, pas de redémarrage automatique depuis la CI.
- Récupérer l'état TrueNAS **sans exporter l'objet brut `app.query`**, susceptible
  de contenir des valeurs sensibles :

```bash
cd /mnt/cpool/compose/nabla-compose
umask 077
sudo midclt call app.query | jq '[.[] | {id, state}]' > /tmp/truenas-app-states-only.json
python3 scripts/truenas/plan-catalog-v2-restart.py \
  --app-query-json /tmp/truenas-app-states-only.json \
  --check-host-secrets \
  --output /tmp/nabla-catalog-v2-restart-plan.json
jq '{stages, apps: [.apps[] | {appId, currentState, stage, action, dependencies, vaultwardenItem, runtimeSecretFiles}]}' \
  /tmp/nabla-catalog-v2-restart-plan.json
```

Ce plan ne lit pas les valeurs de secrets et ne modifie **aucun** conteneur.
Le statut `present-root-only` ne signifie **pas** que les clés sont valides.
`missing` ou `weak-permissions-or-ownership` impose un diagnostic préalable.

## 2. Pré-vérification Vaultwarden (opérateur non-root)

```bash
# Avec une session BW_SESSION déverrouillée, dans le shell non-root :
python3 scripts/secrets/inventory_vaultwarden.py --json

# Pour une application déjà présente dans le manifeste :
python3 scripts/secrets/materialize_runtime.py --app litellm --verify
python3 scripts/secrets/materialize_runtime.py --app homarr --verify
python3 scripts/secrets/materialize_runtime.py --app ntopng --verify
```

`inventory_vaultwarden.py` vérifie unicité et présence de l'item
`nabla/prod/<app>` dans le dossier configuré. `materialize_runtime.py
--verify` compare le rendu des champs requis **en mémoire et via un fichier
temporaire protégé** avec le fichier déjà installé : pas de valeur en log ni
de `BW_SESSION` envoyée à `sudo`. Ne pas remplacer une clé manquante par
une valeur inventée, ni considérer le nom de l'item comme preuve de ses champs.
`--install` seulement après confirmation de la source et des valeurs.

Les apps sans item manifeste ou sans fichier runtime explicite sont marquées
non vérifiées, pas `secret_ok`. En présence d'une erreur ou d'un secret
manquant, leur redémarrage reste **à bloquer** jusqu'à recette.

## 3. Deux vagues ordonnées

**Vague A, actuelle `RUNNING`** : préparer un redéploiement progressif
(`app.redeploy`) des apps **déjà en fonctionnement**, en respectant les
dépendances Backstage inter-Apps et en contrôlant les secrets. L'ordre
des sous-vagues vient de `stages.running-first` dans le rapport.
Conserver un seul redéploiement à la fois sur les services stateful et
surveiller l'impact des dépendants. Un service `RUNNING` dont une dépendance
est non-running ne doit pas être redéployé aveuglément.

**Vague B, autres états** : sélectionner les Apps `STOPPED` après la vague A ;
contrôler leurs paramètres et les secrets. Les états `ERROR`, `CRASHED` ou
`DEPLOYING` nécessitent un diagnostic, les Apps `planned/disabled` une
décision explicite. Aucune relance massive des 143 identités déclarées :
**un service Compose n'est pas nécessairement une TrueNAS App individuelle**.

Le planner est volontairement **read-only** : aucune option `--apply`.
La migration ne planifie pas l'arrêt de services à partir du seul état
déclaratif ; elle attend un snapshot runtime actuel.

## 4. Conditions d'acceptation après chaque app

- TrueNAS `app.query` : état `RUNNING` attendu (ou app `STOPPED` selon
  décision explicite), conteneurs stables et absence de restart loop.
- Docker/Compose : healthcheck vérifié, absence de violation sur les fichiers
  secrets et aucun chemin vers un vieux `.env.secrets` non normalisé.
- Gatus : consulter l'endpoint et ses conditions **natives**, pas seulement un
  port ouvert ; AutoKuma/Uptime Kuma et Prometheus apportent des preuves
  complémentaires. Une sonde échouée ne prouve pas à elle seule `DOWN`.
- FastAPI : vérifier la disponibilité et la réconciliation avec la
  **même `catalogRevision`** que le dépôt, sans télécharger de clé depuis un
  navigateur. Conserver `observedAt` et la provenance.
- Site Alban : la clé Vercel volontairement invalide entraîne
  `access-denied`/HTTP 503 privé sans fallback vers v1 ; vérification positive
  distincte une fois la vraie clé fournie.

Ne pas émettre les logs Docker bruts, la sortie `bw`, ou les détails privés de
`app.query` dans une issue GitHub. Les rapports affichent uniquement des
états et identifiants déclaratifs.

## 5. Correspondances réutilisables

`catalog/generated/identity-map.json` est un **crosswalk déterministe**
issu des labels Compose et de `config/monitoring/gatus-endpoints.yml`.
Chaque `mapping` fournit `entityRef`, `sourceType`, `sourceId`,
`evidence` et `catalogRevision` au niveau du rapport.

Les observations des outils Scanopy, ntopng, Akvorado, Cartography/Neo4j,
Prometheus et FastAPI se joignent ensuite via une identité vérifiée avec
`source`, `observedAt`, `confidence` et provenance. Aucune IP/URL découverte
ne crée un identifiant Backstage. `unresolved` doit être examiné, non
supprimé pour améliorer artificiellement la couverture.

## État de livraison

La génération du plan, les tests hors-ligne et le contrôle des fichiers sont
implémentés ; **aucun redémarrage, vérification Vaultwarden live, ni recette
Gatus/TrueNAS n'a été exécuté** depuis cette PR.
\n**Contrat de corrélation maintenant convergé :** les 85 sondes Gatus natives\nont une correspondance canonique Backstage dans\n`catalog/generated/identity-map.json` (`unresolved: []`), tandis que les 143\nentrées Homarr sont matérialisées par les 153 entités du catalogue v2.\n