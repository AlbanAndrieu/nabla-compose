# OpenClaw Workstation — roadmap opérationnelle dédiée

> **30 octobre 2026 — Host-aware + cron GitOps** : scripts de diagnostic Workstation/TrueNAS séparés et sorties humaines compactes ; message versionné du digest avec `ITEMS_PER_SECTION = 5`, reconciler `plan/check/apply` sécurisé sur l'ID du job existant, sans injection de secrets ni création de cron. Voir le [runbook d'application](runbooks/openclaw-gitops-cron-host-routing-20261030.md). L'apply, le heartbeat et le cutover restent non effectués sur le runtime.


> **Heartbeat restauré en candidat (30 octobre 2026) :** inventaire de 14 fonctions historiques conservé dans `apps/openclaw/workstation/heartbeat-restoration.policy.json`, avec une checklist native courte dans `HEARTBEAT-RESTORED.candidate.md` et des cadences historiques séparées non activées. Aucun runtime activé, aucune copie des secrets des sauvegardes. Le nouveau diagnostic `just openclaw-litellm-dual-logs-check` exige l'accès distinct aux deux proxies ; un seul accessible reste `partial_or_unverified`. [Runbook](runbooks/openclaw-recovery-gates-20261028.md).

> **Mise à jour du code : 30 octobre 2026.** Les PR [#289](https://github.com/AlbanAndrieu/nabla-compose/pull/289) et [#292](https://github.com/AlbanAndrieu/nabla-compose/pull/292) sont **fusionnées**. Les diagnostics d'alignement, de 429, de digest et de sessions sont versionnés mais l'activation systemd et la réparation effective du runtime ne sont **pas attestées**. Voir le [runbook dédié](runbooks/openclaw-recovery-gates-20261028.md).
>
> **Durcissement en cours :** contrôles `cooldown` et `agent:cron:main` à échec fermé, chemins Node des diagnostics dérivés du contrat de version. Ne pas confondre résultat d'un test local et preuve runtime.
> Périmètre : OpenClaw Workstation (agents `main`/`cron`), LiteLLM
> Workstation en amont, politiques et tâches planifiées. Le runtime
> TrueNAS et ses secrets restent distincts. Cette roadmap ne remplace
> pas `docs/roadmap.md` pour l'infrastructure générale.

## État et preuves

| Chantier | Code | Validation locale | Validation runtime |
| --- | --- | --- | --- |
| Auth /v1/models | Sonde OpenRAG corrigée ; préflight TrueNAS vérifié ; contrôle source Vaultwarden | **39/39 PASS** avant correction `jsonschema` ; nouvel essai à recevoir | Workstation HTTP 200 ; conteneur TrueNAS running ; FastAPI scoped key absente du fichier et du conteneur ; Vaultwarden non interrogé |
| Récupération ancienne config `nabla` | Inventaire limité aux politiques, pas de secrets | 5/5 PASS ; fichiers disponibles dans clone git-crypt déverrouillé | Pas de copie ou application |
| Digest | Manifeste non secret et diagnostic du skill | 3/3 manifeste PASS ; diagnostic upstream 16 tests non revalidés après dernière édition | Job réel conservé ; réussite éditoriale à confirmer |
| Sessions `cron` | Diagnostic complet, maintenance native `--dry-run`/`--enforce` | 5/5 parent + 6/6 maintenance PASS | **ACCEPTED maintenance** : 21 → 21, `pruned=0` ; parent toujours absent |
| HEARTBEAT | Politique native non générative ; briefing séparé, récupération historique documentée | 3/3 contrats PASS | Jobs anciens non restaurés |
| Copies historiques | Inspection privée et correction opt-in `0600` | 4/4 inspection + 8/8 tests PASS | **ACCEPTED** : 3 fichiers en 0600 ; inspection finale 3 `private` |
| LiteLLM TrueNAS cutover | Préflight et rollback déclarés | Contrats seulement | NON AUTORISÉ avant fermeture P0 Workstation |

**Limites probatoires :** les contrats unitaires ne prouvent ni
le fonctionnement effectif du Gateway ni l'authentification de
`/v1/models`. Chaque `ACCEPTED runtime` requiert une nouvelle
preuve datée sur la machine concernée.

## Décision P0 — Conserver l'identité FastAPI upstream (27/10)

**Décision opérateur : CONSERVER** `LITELLM_FASTAPI_WORKSTATION_API_KEY`,
sans réutiliser `LITELLM_IDE_API_KEY` ni la master key.
Chaîne d'autorité attendue (noms de fichiers et de champs uniquement,
**aucune valeur secrète dans Git**) :

- LiteLLM Workstation : clé virtuelle `fastapi-sample-upstream`,
  autorisée uniquement pour `qwen`, définie par la politique
  `config/fastapi-sample/litellm-key-policy.json`.
- Source de référence : Vaultwarden, item `nabla/prod/litellm`,
  champ masqué `LITELLM_FASTAPI_WORKSTATION_API_KEY`.
- Cache runtime TrueNAS : `/mnt/cpool/secrets/runtime/litellm/.env.secrets`
  (root:root 0600), injecté via `apps/litellm/compose.yml:env_file`.
- Fichier de transit **facultatif et non attesté** sur Workstation :
  `~/.local/share/nabla-compose/fastapi-litellm/workstation.key`.
- Consommateur : route `fastapi-qwen` dans
  `apps/litellm/config.yaml`, proxifiée sur Workstation
  `172.17.0.57:4000/v1`.

**Dernière preuve runtime TrueNAS attestée** : version
`TrueNAS-26.0.0-BETA.2`, conteneur `litellm`
`selected/running`, version SDK `1.106.4`,
`LITELLM_IDE_API_KEY=present` mais
`LITELLM_FASTAPI_WORKSTATION_API_KEY=absent`.
Contrats **33/33 PASS** (3 OpenRAG, 8 pytest, 22 upstream),
préflight runtime code 2 **correctement fail-closed**.

**Prochaine action P0 : inventaire en lecture seule** du champ
Vaultwarden, de son rendu dans le fichier TrueNAS et de
l'injection au service. Ne pas supposer que la clé existe déjà
sur Workstation. Si absente à la source, appliquer le runbook
`docs/runbooks/fastapi-sample-litellm.md` pour un
provisionnement *scope qwen*, budget plafonné et validation
du proxy, uniquement après revue du risque de doublon.
Ne pas exécuter `--install` / `--apply` ou redéployer
sur une simple preuve de variable manquante.

### Dernier contrôle du fichier de secrets LiteLLM

La commande opérateur exécutée **avec sudo** :

```bash
sudo grep -qE '^LITELLM_FASTAPI_WORKSTATION_API_KEY=.+' \
  /mnt/cpool/secrets/runtime/litellm/.env.secrets
```

a abouti à `Clé absente ou fichier inaccessible`. La condition
regroupe plusieurs cas : fichier absent ou inaccessible,
variable non déclarée, ligne précédée de `export`/espaces,
valeur vide. **On ne peut donc pas conclure à l'absence
de la clé dans Vaultwarden ni même à l'absence du fichier.**
La variable est en revanche **absente du conteneur TrueNAS**
d'après le préflight v4 reçu : hôte `truenas_verified`,
cible `litellm` running, variable FastAPI `absent`,
IDE `present`, SDK `1.106.4`, liveness Workstation
`http_200`, exit 2 (fail closed). Les **33/33 tests de
contrat** étaient PASS (3 OpenRAG + 8 auth pytest +
22 upstream unittest).

**Prochain gate P0 = provenance**, sans rotation :
1. Inspecter le type/propriétaire/mode du fichier canonique
   via `sudo stat` ; ne pas en afficher les valeurs.
2. Compter uniquement les déclarations de la clé dans ce
   fichier (zéro, une, doublons) avec une commande
   expurgée ; distinguer source manquante et injection
   conteneur obsolète.
3. Via une session Vaultwarden déverrouillée **non root**,
   vérifier l'existence du champ
   `nabla/prod/litellm:LITELLM_FASTAPI_WORKSTATION_API_KEY`
   sans afficher sa valeur. L'opération
   `python3 scripts/secrets/materialize_runtime.py --app
   litellm --verify` est en lecture seule sur la cible,
   mais peut échouer pour une autre divergence du même item.
4. Si la source existe, préparer la matérialisation complète
   en conservant les autres champs et vérifier l'injection
   avant redéploiement manuel. Si elle n'existe pas,
   inspecter le provisionnement Workstation existant
   avant de générer une clé scoped `qwen`.

**Interdit à ce stade :** `--install`, `--apply`,
redémarrage automatique du conteneur, affichage des
secrets, recours à la master key, déploiement TrueNAS.
La panne `GET /v1/models` sans Bearer reste
**non attribuée** : ne pas l'imputer automatiquement
à cette absence de variable.

### Clé FastAPI upstream : source canonique incomplète — preuve finale

**TrueNAS runtime :** `/mnt/cpool/secrets/runtime/litellm/.env.secrets`
est un fichier régulier `root:root 0600`, taille 5457 octets.
La vérification tolérant les espaces initiaux et `export`
retourne `fastapi_key_declaration_count=0`.
Le fichier est lisible mais **ne contient aucune déclaration**
de `LITELLM_FASTAPI_WORKSTATION_API_KEY` : on ne
peut pas imputer ce cas à un `env_file` Docker mal chargé.
Le conteneur TrueNAS `litellm` est running, la clé IDE
est présente et la clé FastAPI absente.

**Nouveau gate [skip ci]** : `just litellm-fastapi-upstream-source-check`
depuis une session opérateur non root avec Vaultwarden
déverrouillé. Le script lit le champ caché exact de
`nabla/prod/litellm`, dossier `TrueNAS`, renvoie
un état fermé, sans valeur secrète. Nouveau contrat offline
`tests/test_litellm_fastapi_upstream_source.py` intégré
à `just litellm-workstation-auth-contracts`. Tests
**non encore exécutés** ; derniers tests déjà reçus
33/33 PASS avant cette extension.

- Si la source est présente, vérifier les écarts avec
  la matérialisation existante avant toute installation
  (les autres clés du même fichier doivent être conservées).
- Si la source manque, contrôler la copie transitoire de
  Workstation puis la clé virtuelle `fastapi-sample-upstream`
  avant tout provisionnement, pour éviter les doublons.
- Pas de changement de secrets, pas de nouvelle clé,
  pas de redémarrage et pas de cutover automatique.

### Diagnostic Vaultwarden bloqué sur dépendance Python (relevé opérateur)

`git pull` puis `just litellm-workstation-auth-contracts`
ont validé **39/39 PASS** (3 OpenRAG, 8 pytest LiteLLM,
22 upstream, 6 source Vaultwarden). Le premier
`just litellm-fastapi-upstream-source-check` a
échoué **avant toute connexion Vaultwarden**, lors
de l'import `jsonschema` introuvable sous
`python3`. **Aucune preuve que la clé ait jamais
été provisionnée ou qu'elle soit absente de Vaultwarden.**
La politique Git et les emplacements ne sont pas des
preuves de génération de clé.

**Correctif [skip ci] :** recherche de `jsonschema`
dans des environnements Python locaux **déjà installés**,
d'abord `NABLA_SECRETS_PYTHON`, puis
`.venv/bin/python`, puis Pythons système,
sans paquet global, GitHub CI, mutation de secret
ou création de clé. Échec fermé et consignes de
`uv sync --group test --locked --offline` si le
cache de dépendances le permet. Le script direct
classe l'absence du module en
`python_dependency_unavailable`, sans traceback ;
un test offline additionnel couvre ce cas (test
non encore exécuté depuis ce correctif).

**Prochaine preuve immédiate** :
`just litellm-fastapi-upstream-source-check`
en session opérateur Vaultwarden existante et,
depuis la Workstation, le `--target workstation
--check` du provisionneur FastAPI (lecture seule,
pas de réseau). Avant une génération éventuelle,
contrôler l'alias `fastapi-sample-upstream`
dans la base LiteLLM Workstation, pour empêcher
une clé virtuelle orpheline/doublon. La décision
reste : **conserver** une clé distincte scoped `qwen`
sans réutiliser la clé IDE/master.

### Génération demandée sur TrueNAS : frontière entre les deux clés

L'opérateur demande de **générer dans LiteLLM TrueNAS**.
Le provisionneur prend désormais en charge le mode explicite
`--target truenas --native-truenas --apply`, qui contacte
le port **local** `127.0.0.1:4000/key/generate` seulement
après preuve `midclt call system.version`. Il crée la
clé `fastapi-sample-staging` pour le premier saut
**FastAPI Sample → LiteLLM TrueNAS**, sans afficher
sa valeur (fichier de transition privé `truenas.key`).
Cette clé sera enregistrée dans Vaultwarden
`nabla/prod/sample-litellm` sous `LITELLM_API_KEY`
lors d'un cutover ultérieur validé. Politique :
`fastapi-qwen`, plafond 8 USD à vie, 5 RPM,
15 000 TPM, concurrence 1.

**ATTENTION :** la variable manquante
`LITELLM_FASTAPI_WORKSTATION_API_KEY` est une clé
**émise par LiteLLM Workstation**, que TrueNAS doit
ensuite consommer pour son second saut. Créer une
clé virtuelle dans LiteLLM TrueNAS ne la rend pas
valide sur Workstation. Cet incident P0 reste donc
ouvert même après création de la clé de premier saut.

La PR #289 prépare le code et le runbook,
**pas une génération runtime** (aucune connexion SSH
ou gestion admin LiteLLM disponible depuis l'agent).
Avant `--apply`, vérifier l'absence de l'alias
`fastapi-sample-staging` dans l'interface **LiteLLM
TrueNAS** ; l'absence dans Vaultwarden n'est pas
une preuve suffisante. La clé master utilisée doit
être celle de **TrueNAS** et reste privée. Aucune
réutilisation de clé IDE, master ou Workstation
comme secret applicatif.

Le code de génération utilise désormais un opener
sans proxy HTTP ambiant et sans suivi de redirection.
La suite de contrats natifs TrueNAS et du routage
à deux proxies est à recevoir après exécution locale.
`--apply` n'a **pas** été exécuté par cet agent.

### P0 Workstation LiteLLM — échec `--apply` non attribué, inventaire sans POST

**Nouvelle preuve opérateur** : 6/6 tests du provisionneur natif
TrueNAS PASS, puis `provision-fastapi-litellm-keys.py
--target workstation --apply` → `BLOCKED:
configuration, transport or secure-storage failure`.
Cet ancien message regroupe toutes les erreurs. Il ne
prouve **ni** une création **ni** une absence de la clé
dans la base du proxy Workstation. Le succès d'une
écriture `workstation.key` reste non attesté.
**Interdiction de relancer --apply sans inventaire.**

**Correctifs PR #289 [skip ci] :**
- Script de diagnostic read-only
  `scripts/workstation/diagnose-fastapi-litellm-workstation-key.py`
  via `just litellm-workstation-fastapi-key-inventory`.
  Vérifie d'abord l'identité Workstation (refuse
  `midclt` TrueNAS ; requiert le conteneur Docker
  exact `litellm-litellm-1` running), puis l'état
  du fichier personnel sans lire sa valeur, HTTP
  `/health/liveliness` et éventuellement un
  GET `/key/list` filtré avec la master Workstation,
  **sans afficher le JSON de gestion ni les clés**.
  Aucune inférence, aucune génération, aucun POST.
- Provisionneur renforcé : un futur `--target workstation
  --apply` bloque avant génération si l'hôte/
  conteneur exact ne peut pas être attesté.
- Tests offline ajoutés pour refus TrueNAS, refus
  de l'hôte inconnu, absence d'alias non confirmée,
  refus de secrets dans l'output et contrôle sans POST.
  **Non exécutés** depuis ces changements.

**Prochaine action unique** : exécuter
`just litellm-workstation-fastapi-key-inventory`
sur Workstation après `git pull --ff-only`,
puis, si local proxy attesté, relancer
**ce seul inventaire GET** dans une session
où `LITELLM_MASTER_KEY` Workstation est fournie
privément. En cas de `alias_exists`, pas de
nouveau provisioning (risque de clé orpheline).
Un `alias_absent_confirmed` avec proxy 200 et
répertoire sécurisé permettra d'envisager une
nouvelle génération `qwen` avec le budget limité.
Ne pas afficher, copier dans Git, ou envoyer
`LITELLM_MASTER_KEY`.

## Réception opérateur — permissions et sessions (27/10, soirée)

- **PERMISSIONS ACCEPTED runtime :** nouvelle suite `8/8 PASS`,
  `openclaw-heartbeat-modes-apply` a modifié les **trois**
  fichiers `0644/0666 → 0600` ; contrôle ultérieur
  `openclaw-heartbeat-copies-check` affiche **trois `private`**
  et aucune extraction/modification de contenu. Clore le gate
  `mode bits` ; revue ACL étendue facultative et distincte.
- **CRON MAINTENANCE ACCEPTED runtime :** suite `6/6 PASS`,
  `--dry-run` puis `--enforce` retournent
  `beforeCount=21, afterCount=21, pruned=0, capped=0,
  missing=0`. La maintenance a été exécutée sans erreur
  mais n'a pas supprimé de session, conformément à la
  politique de rétention active.
- **PARENT ENCORE ABSENT :** `openclaw-cron-parent-check`
  renvoie `absent_in_reported_complete_catalog` sur les
  21 sessions. Ne pas qualifier le nettoyage de restauration
  de `agent:cron:main`. L'historique pouvant être perdu,
  une **suppression ciblée** avec prévisualisation reste
  facultative ; identifier au préalable le mécanisme UI
  de création de nouvelle session, sans réinitialiser les clés.
- **LITELLM TOUJOURS EN ÉCHEC :** un nouvel événement
  `No api key passed in.`, `user_api_key=null`,
  zéro token, UA `litellm/1.106.4`, IP source
  `172.17.0.24`. Un `GET /v1/models` anonyme
  **n'est pas** un événement 429. L'attribution exacte
  exige un contrôle des variables **dans le conteneur
  TrueNAS** et du client SDK.
- Le nouveau préflight `diagnose-workstation-litellm-upstream-auth.py`
  **bloque explicitement** les clés d'upstream manquantes et
  fournit la version du SDK LiteLLM du conteneur, sans afficher
  les valeurs ni envoyer de requêtes de modèles. Un match
  de version avec l'UA serait une **corrélation**, non une
  identification certaine de l'appelant.

```bash
# Workstation : suite offline, pas de modèle
just litellm-workstation-auth-contracts

# TrueNAS : depuis un checkout de la PR à jour, sans inférence
just litellm-workstation-upstream-auth-check
```

**Pas de cutover avant les preuves runtime.** Un statut
`all_present_unvalidated` indique seulement que les deux
variables sont non vides ; il ne prouve pas validité, scopes
ou injection d'un Bearer sur le client fautif.

## P0 — Correction de provenance des hôtes (27 octobre)

**Rectification de l'opérateur :** `litellm-litellm-1` est le
conteneur **Workstation**, et non TrueNAS. Les diagnostics
précédents ont mélangé des relevés de deux machines : leurs
conclusions attribuant `litellm-litellm-1` à TrueNAS sont
**invalidées**. Il est incorrect de corriger les labels ou
les noms Docker à l'aveugle sans identifier d'abord l'hôte.

**Preuves réellement reçues :**

| Preuve | Portée |
| --- | --- |
| `litellm-litellm-1` Up 3 days healthy | Workstation, confirmé par l'opérateur |
| `litellm` Up 24 hours healthy, autre relevé | Conteneur à confirmer depuis une session TrueNAS |
| `docker exec litellm` : `LITELLM_IDE_API_KEY=present`, `LITELLM_FASTAPI_WORKSTATION_API_KEY=absent` | Valeur observée dans un conteneur nommé `litellm` ; **provenance machine à attester** |
| `GET /v1/models` : `No api key passed in.`, 0 token, source `172.17.0.24` | Client exact toujours non attribué |
| Dernier contrat `just litellm-workstation-auth-contracts` | **31/31 tests PASS** (3 OpenRAG + 8 pytest + 20 unittest), **avant** le correctif d'identité hôte |

**Correctif fail-closed #289 :**
- Appeler `midclt call system.version` et vérifier une version
  `TrueNAS-...` **avant toute découverte Docker ou requête HTTP**.
  Sans preuve, `host_context=unverified_not_inspected` et code 2 ;
  aucune inspection de la Workstation n'est confondue avec TrueNAS.
- Sur TrueNAS vérifié uniquement, sélectionner la seule instance
  **running nommée exactement `litellm`**. Le nom
  `litellm-litellm-1` est exclu du sélecteur TrueNAS.
  Les vérifications du statut, des clés présentes/absentes et
  de la version SDK utilisent le même identifiant interne,
  jamais imprimé.
- Les valeurs des deux variables restent privées. Un résultat
  `missing_runtime_upstream_key` prouvera l'absence d'au
  moins une valeur **dans le conteneur TrueNAS réellement
  sélectionné**, mais ne prouvera pas l'identité du
  client `/v1/models`.
- Aucun auto-provisionnement, rotation, redémarrage Docker,
  changement de proxy ou bascule de routes.

```bash
# Tests locaux d'abord, sans réseau ni mutation :
just litellm-workstation-auth-contracts

# Cette commande est STRICTEMENT pour une console TrueNAS :
just litellm-workstation-upstream-auth-check
```

**Attendu sur TrueNAS :**
`host_context=truenas_verified`,
`truenas_container_selection=selected`,
`truenas_docker_container_name=litellm`,
`truenas_docker_container_status=running`.
Un résultat `host_context=unverified_not_inspected` appelle
d'abord une vérification de l'hôte et du middleware, **pas
une modification des secrets**.

La suite modifiée pour ce correctif n'est pas encore attestée
exécutée. L'enquête P0 continue ensuite sur la provenance
de la clé FastAPI, sa matérialisation depuis Vaultwarden
dans le fichier privé TrueNAS, et l'identité du client SDK
sans Bearer.

## P0 — Stabiliser LiteLLM Workstation

- [x] Corriger le GET anonyme `/v1/models` du diagnostic OpenRAG
  (code #289, pas encore déployé sur TrueNAS).
- [x] Définir classificateur sans secrets `MISSING_CLIENT_API_KEY`.
- [x] Valider les tests locaux : 16/16 LiteLLM et 18/18 OpenRAG.
- [ ] **Attribuer la trace** `GET /v1/models`, source
  `172.17.0.24`, User-Agent `litellm/1.106.4` :
  rechercher le client TrueNAS exact avant de modifier ses clés.
  Ni User-Agent ni IP ne prouvent le composant.
- [ ] Vérifier liveness/readiness depuis les deux hôtes et
  la présence des variables d'upstream avec
  `just litellm-workstation-upstream-auth-check` sur TrueNAS.
- [ ] Qualifier séparément le 429 du chat `main` (clé scoped,
  quotas, spend, fenêtre, origine exacte et modèle), sans augmentation
  de budget ni appel modèle de diagnostic.
- [ ] Fin P0 : clients connus authentifiés, aucune sonde anonyme
  sur endpoint protégé, chat `main` accepté et preuve de 429 attribuée
  ou disparue sur fenêtre d'observation définie.

## P1 — Sessions : nettoyage maîtrisé (perte historique acceptée)

**Décision du propriétaire le 27/10** : le contenu historique des
sessions peut être perdu. Cela **n'autorise pas** la suppression des
identités, credentials, automatisations et caches vectoriels.

- [x] Lire catalogue `cron` complet : 21 sessions, `hasMore=false`,
  session principale `agent:cron:main` absente.
- [x] Définir un mécanisme natif `openclaw sessions cleanup`
  limité à l'agent `cron` dans un script redacted et des recettes
  explicites `--check` / `--apply` (PR #289).
- [ ] Exécuter le **plan de nettoyage** sur Workstation ;
  inspecter les compteurs et refuser tout état ambigu.
- [ ] Appliquer la maintenance `--agent cron --enforce`
  uniquement après validation du plan et hors tâche en cours.
- [ ] Vérifier que les jobs `daily-tech-news-digest`, les
  connexions et le modèle `cron` restent configurés.
- [ ] Si `/chat/cron` échoue encore, créer une nouvelle session
  via le parcours UI supporté plutôt qu'un lien parent invalide.
  **La maintenance ne crée pas `agent:cron:main`.**
- [ ] Option ultérieure : suppression individuelle ciblée via
  `openclaw sessions delete <clé> --agent cron --dry-run`,
  puis `--yes` ; jamais de reset config+creds+sessions, ni
  `rm -rf ~/.openclaw`.

## P1 — Sécuriser les copies HEARTBEAT

- [x] Inventorier les trois fichiers sans lire leur contenu :
  `.before-fix` écrivable par d'autres ; heartbeat historique
  et archive 993 378 302 octets lisibles par d'autres.
- [x] 6/6 tests du premier garde `0600` PASS.
- [ ] Confirmer le correctif du répertoire parent lié symboliquement
  dans le clone `nabla` (revue stricte de chemin canonique/inode).
- [x] `just openclaw-heartbeat-modes-test` : **8/8 PASS**.
- [ ] `just openclaw-heartbeat-modes-check`.
- [x] **Opt-in** `just openclaw-heartbeat-modes-apply`
  lorsque les trois identités attendues sont reconnues.
- [x] `just openclaw-heartbeat-copies-check` → exit 0 et
  trois classes `private`, puis examen des ACL supplémentaires
  si nécessaires.

## P2 — Migration non secrète `nabla` → `nabla-compose`

- [x] Identifier `git-crypt` dans le dépôt privé et les fichiers
  historiques localement lisibles.
- [x] Récupérer **les fonctions** du heartbeat : workboard,
  CalDAV, santé, observabilité, Gmail/WhatsApp, rapports périodiques ;
  aucune tâche lancée automatiquement par cette récupération.
- [x] Séparer Workboard `openclaw workboard list` et Tasks
  `openclaw tasks list` dans `MORNING_BRIEFING.md`.
- [ ] Revoir `AGENTS.md`, `SOUL.md`, `TOOLS.md`, les skills
  et leurs dépendances, puis créer de nouvelles versions
  expurgées dans `apps/openclaw/workstation/`.
- [ ] Préserver `IDENTITY.md`, `USER.md`, `.env`, modèles
  de clés, profils, bases SQLite et listes de contacts/sources
  privées **hors Git public**.
- [ ] Préparer le reconcileur GitOps de cron idempotent
  (`list / diff / apply` séparés) et les tests de non-duplication.
- [ ] Pin versions/hash des skills et ACL MCP ; aucun chargement
  automatique d'un MCP non approuvé dans l'agent `cron`.

## P2 — Workboard, briefing et HEARTBEAT

- [x] Reprendre les rubriques de l'ancien briefing :
  métriques, agendas, alertes, workboard, actions effectuées.
- [ ] Inventorier les timers/cron réellement actifs
  (ne pas confondre intention du document ancien et état runtime).
- [ ] Planifier, un par un, des collecteurs **déterministes**
  (Gatus/Prometheus, CalDAV et éventuellement WhatsApp)
  avec identité, ACL, journal de résultat et borne temporelle.
- [ ] Créer au besoin un unique briefing quotidien isolé et
  plafonné, avec sources datées ; coût et succès éditorial suivis.
- [ ] Maintenir le heartbeat natif non génératif jusqu'à
  preuve de stabilité de la facturation LiteLLM. Ne pas réactiver
  les cadences de 15 min / 30 min / 1 h directement dans le modèle.

## P3 — Migration contrôlée LiteLLM Workstation → TrueNAS

- [ ] Confirmer aliases `gpt-4.1`, `gpt-4.1-mini` réellement
  exposés par TrueNAS, clés `main`/`cron` distinctes persistées
  et budgets/quotas mesurés.
- [ ] Préflight authentifié et scopes sans publication des clés,
  aucune inférence de sonde routinière.
- [ ] Cutover **explicite** des providers OpenClaw avec point de
  rollback Workstation, puis vérification des jobs.
- [ ] Migration des embeddings/indices et RAG traitée séparément ;
  aucune substitution silencieuse des modèles vectoriels.

## Commandes opérateur

```bash
just litellm-workstation-auth-contracts
just truenas-openrag-startup-test
just openclaw-cron-parent-check
just openclaw-cron-session-maintenance-test
just openclaw-cron-session-maintenance-check
just openclaw-heartbeat-modes-test
just openclaw-heartbeat-modes-check
```

Voir également [runbook GitOps/workstation](runbooks/openclaw-workstation-gitops-migration-20261027.md),
[runbook digest](runbooks/openclaw-tech-digest-invalid-top-20261027.md)
et [récupération heartbeat](../apps/openclaw/workstation/LEGACY_HEARTBEAT_RECOVERY.md).

Aucun marqueur « DONE runtime » ne peut être posé à partir d'un
`[skip ci]` ou d'un test unitaire exécuté hors de la machine.
