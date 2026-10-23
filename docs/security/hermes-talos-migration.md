# Hermes sur Talos — migration du service Compose vers une architecture broker/sandbox (ADR, non déployée)

**2026-10-23 · Statut : proposition. Aucun déploiement, namespace, secret ni
changement de CNI/CSI.** Prolonge l'ADR
[Hermes Secure by Design](./hermes-secure-by-design.md) et le
[service Compose](../../apps/hermes/README.md) ; ne les remplace pas.
L'App native TrueNAS `hermes-agent` est retirée (décision 2026-10-23) au
profit de `apps/hermes`.

## Contexte

Le service `apps/hermes/` (statut catalogue `planned`) est un gateway
Compose en lecture seule : tous les
toolsets d'exécution sont coupés, seul le MCP `nabla_observe` est autorisé.
Pour qu'Hermes puisse un jour **agir** (préparer une PR, valider un Compose,
lancer un lint) sans recevoir de shell sur TrueNAS, il faut une frontière
d'exécution externe : le « typed external task broker » que l'ADR Secure by
Design reporte.

Le cluster Talos (v1.13.9, 3 nœuds, `truenas-csi`) décrit dans
[kubernetes-platform-tools.md](../kubernetes-platform-tools.md) rend
possible le modèle suivant, aligné sur le projet amont
kubernetes-sigs/agent-sandbox :

```text
Hermes gateway (StatefulSet, 1 réplica, toolsets d'exécution coupés)
  └─ plugin sandbox (adaptateur fin, aucun droit Kubernetes)
       └─ sandbox-broker (seul détenteur des droits namespace-scoped)
            └─ kubernetes-sigs/agent-sandbox
                 SandboxTemplate / SandboxClaim / Sandbox / SandboxWarmPool
```

## Décision proposée

1. **Cible runtime : Talos**, pas Compose. Le service Compose `apps/hermes` reste la phase 1
   et la référence de sécurité ; il n'est pas réutilisé comme cible finale.
2. **Pas de terminal local.** `terminal`, `code_execution`, `file`,
   `browser` restent dans `agent.disabled_toolsets`. Toute exécution passe
   par le broker vers un pod sandbox éphémère.
3. **Chart Helm** : ne consommer qu'un chart publié sous licence OSS
   compatible ; jamais de code tiers non publié ou sans licence.
   **Phase 2 retenue (2026-10-23) : bundle Kustomize local**
   `kubernetes/hermes/`, sans dépendance à un chart ; un chart pourra le
   remplacer en phase 3 s'il respecte les mêmes contrats.
4. **Config en GitOps** : `config.yaml` est `config/hermes/config.yaml`
   lui-même (source unique avec le service Compose), monté en lecture seule par
   `subPath`, dashboard désactivé. La configuration n'est jamais modifiable
   depuis l'UI ou un canal de chat.
5. **Image par digest** obligatoire (même règle que `preflight.py`),
   SDK d'observabilité éventuel intégré à une image dérivée, jamais installé
   au démarrage du pod.

## Bloqueurs constatés dans ce dépôt (2026-10-23)

| # | Constat | Source | Conséquence |
| --- | --- | --- | --- |
| B1 | CNI = **Flannel** ; l'application réelle des `NetworkPolicy` n'est **pas prouvée** | [truenas-talos-bootstrap.md](../truenas-talos-bootstrap.md), [kubernetes-security-headlamp-roadmap.md](../kubernetes-security-headlamp-roadmap.md) (P1 ouvert) | Sans enforcement, la migration n'apporte pas le filtrage egress qui manque au bridge Compose. **Gate bloquant**, levé uniquement par `scripts/talos/smoke-networkpolicy-enforcement.sh` au vert. |
| B2 | StorageClass `nabla-truenas-nfs` : NFS 4.1, `reclaimPolicy: Delete` | `kubernetes/truenas-csi/storageclass-nfs.yaml` | `/opt/data` contient des fichiers SQLite (`state.db*`) : verrouillage sur NFS à éprouver ; `Delete` détruirait l'état Hermes à la désinstallation. **Partiellement levé** : classe `nabla-truenas-nfs-retain` (`Retain`, `WaitForFirstConsumer`, mêmes paramètres NFS) dans `kubernetes/hermes/`. Reste à prouver en runtime : un seul écrivain, intégrité de `state.db` après redémarrage et snapshot ZFS restaurable ; sinon stockage bloc/local. |
| B3 | s6 démarre en root puis descend à l'UID 10000 | ADR Secure by Design, `apps/hermes/compose.yml` | PSA `restricted` impossible pour le gateway : namespace `hermes` en `baseline`, exception documentée. Les sandboxes, elles, restent `restricted`. |
| B4 | ~~Budget incohérent~~ **Tranché (2026-10-23)** : 20 EUR par mois calendaire | `config/hermes/litellm-key-policy.json` | Convertir en plafond USD prudent au provisionnement de la virtual key (taux et reset documentés). |
| B5 | Secrets K8s : Vault en phase 1 sur NFS, External Secrets non déployé | [kubernetes-platform-tools.md](../kubernetes-platform-tools.md) | Tant qu'ESO n'est pas accepté, Secret Kubernetes créé manuellement par l'opérateur, jamais commité. |

## Correspondance service Compose → Kubernetes

| Service Compose | Kubernetes | Note |
| --- | --- | --- |
| `cap_drop: [ALL]` + `CHOWN/SETUID/SETGID` | `containerSecurityContext.capabilities` | Ne pas ajouter `DAC_OVERRIDE` sans preuve runtime. |
| `no-new-privileges` | `allowPrivilegeEscalation: false`, `seccompProfile: RuntimeDefault` | |
| `mem_limit`, `cpus` | `resources` (limites 2 CPU / 4 Gi) | |
| `pids_limit: 128` | aucun équivalent par pod | `podPidsLimit` kubelet au niveau nœud Talos ; écart accepté et documenté. |
| bind `/mnt/cpool/hermes/data` → `/opt/data` | PVC `Retain` (voir B2) | Snapshot ZFS avant chaque montée de version. |
| `config.yaml` read-only | ConfigMap générée depuis le même fichier, `subPath` en lecture seule | |
| `.env.secrets` 0600 | `Secret` opérateur → plus tard ESO/Vault | Uniquement bot token, allowlist, virtual key LiteLLM. |
| bridge `hermes` sans ACL egress | `NetworkPolicy` default-deny + allowlist | Après B1. |
| overlay `compose.api.yml` sur `intranet` | Service `ClusterIP` `:8642`, sans Ingress | Clé API par client. |
| aucun dashboard | dashboard désactivé | Si un jour activé : OIDC Keycloak, LAN/VPN seulement. |
| `readonly_mcp.py` monté | ConfigMap montée en lecture seule | Le MCP reste l'unique outil d'observation. |

### Egress allowlist cible du gateway

DNS (CoreDNS), LiteLLM (route/virtual key Hermes uniquement), Prometheus
(lecture), sandbox-broker (`ClusterIP`), Telegram/Discord. Tout le reste est
refusé : API TrueNAS, socket-proxy Docker, pfSense, Vaultwarden, plages
RFC1918 non listées, `169.254.169.254`, IPv6 non prévu.

`NetworkPolicy` ne connaît pas les FQDN : Telegram/Discord passent par HTTPS
public (`0.0.0.0/0` hors plages privées, link-local, CGNAT et loopback). Un
filtrage par nom exigera un CNI comme Cilium.

## Manifestes phase 2 : `kubernetes/hermes/`

**Non appliqués.** Traduction directe du service Compose : namespace `hermes`
(PSA `baseline`, audit/warn `restricted`), StorageClass `Retain`,
ServiceAccount sans token, Service headless sans port, StatefulSet à un
réplica, `NetworkPolicy` default-deny + egress minimale. Contrat figé par
`tests/test_kubernetes_hermes_contract.py`.

```bash
# Rendu et validation hors cluster (sans secret, sans apply)
kubectl kustomize --load-restrictor LoadRestrictionsNone kubernetes/hermes \
  | kubeconform -strict -summary
```

Avant tout apply, par l'opérateur uniquement :

1. Gates B1 (smoke NetworkPolicy vert) et phase 1 acceptés.
2. Remplacer `sha256:REPLACE_WITH_VERIFIED_DIGEST` dans
   `kubernetes/hermes/kustomization.yaml` par le digest vérifié ; le
   placeholder fait échouer le pull, c'est voulu.
3. Arrêter le service Compose `apps/hermes` (l'App native étant retirée), ou
   utiliser des bots distincts : jamais le même bot token sur deux gateways.
4. Créer le Secret `hermes-runtime` dans le namespace `hermes` depuis
   `/mnt/cpool/secrets/runtime/hermes/.env.secrets` (`kubectl create secret
   generic hermes-runtime --from-env-file=...`), sans jamais afficher son
   contenu ni le commiter.
5. Vérifier en runtime : UID effectif 10000 et `CapEff` nul du gateway,
   flux refusés hors allowlist, redémarrage sans perte de `state.db`.

## Sandbox : règles de conception

- Broker **sans état** : chaque session est reconstruite depuis le
  `SandboxClaim`. L'expiration est confiée au contrôleur amont : chaque claim
  porte `spec.lifecycle.shutdownTime` et `shutdownPolicy: Delete` (défaut
  amont : `Retain`, à ne jamais laisser), jamais un timer de process.
- Le broker impose `automountServiceAccountToken: false` sur chaque claim ;
  le `SandboxTemplate` approuvé reste la source unique d'image, de
  `securityContext` et de ressources. Pas de surcharge par requête.
- Namespace `hermes-sandbox` en PSA `restricted`, UID non-root, rootfs
  read-only, seuls `/workspace` et `/tmp` en écriture, egress refusé par
  défaut (exceptions explicites : forge Git, registre d'images miroir).
- Template homelab initial `hermes-homelab-offline` : **isolé du réseau**
  (ni ingress, ni egress, ni DNS), git sur un workspace fourni, just,
  pre-commit, `docker compose config --quiet --no-interpolate
  --no-env-resolution`. Un second template « PR GitHub » (HTTPS vers la forge
  seulement, `gh` avec token **fine-grained limité aux PR**, jamais de merge)
  fera l'objet d'une revue distincte. Pas de `kubectl`, pas de socket Docker,
  pas de SSH TrueNAS/pfSense, pas de clé maître LiteLLM.
- Le broker publie un catalogue de capacités par template, sans aucune
  valeur sensible ; Hermes le consulte au lieu de sonder l'environnement.

## Manifestes phase 4 : `kubernetes/hermes-sandbox/`

**Non appliqués.** Frontière d'exécution, posée avant que le broker existe :

| Fichier | Contrôle |
| --- | --- |
| `namespace.yaml` | PSA `restricted` en enforce/audit/warn. |
| `quota.yaml` | 4 pods max, CPU/mémoire/stockage éphémère bornés, **0 PVC, 0 Service** ; `LimitRange` par défaut. |
| `networkpolicy.yaml` | Default-deny namespace, indépendant de la politique gérée par le contrôleur : un template ne peut jamais être plus large que ses propres règles. |
| `sandboxtemplate.yaml` | `hermes-homelab-offline` (`extensions.agents.x-k8s.io/v1beta1`) : non-root UID 1000, rootfs read-only, `drop: [ALL]`, sans token SA, `emptyDir` bornés, réseau `ingress: []` / `egress: []`. |
| `broker-rbac.yaml` | `Role` namespacé pour le ServiceAccount `hermes-sandbox-broker` du namespace `hermes-broker` : claims (création/suppression), lecture des templates, sandboxes, pods, `pods/exec`, `pods/log`. **Aucun** accès aux Secrets, ConfigMaps, templates en écriture, warm pools ni création directe de pods. |

Contrat figé par `tests/test_kubernetes_hermes_sandbox_contract.py`.

```bash
kubectl kustomize kubernetes/hermes-sandbox \
  | kubeconform -strict -summary -ignore-missing-schemas
```

Reste à faire avant tout apply :

1. Installer le contrôleur kubernetes-sigs/agent-sandbox depuis une release
   épinglée et revue (CRD `agents.x-k8s.io` et `extensions.agents.x-k8s.io`
   en `v1beta1`), dans `agent-sandbox-system`.
2. Construire et signer l'image `hermes-homelab-sandbox` (non-root UID 1000,
   sans `kubectl` ni identifiants), puis remplacer le placeholder de digest.
3. Écrire ou choisir le broker (namespace `hermes-broker`, API typée,
   authentification par jeton, `shutdownTime` obligatoire sur chaque claim)
   et le plugin Hermes ; ouvrir alors l'egress du gateway vers le broker.
4. Tests d'évasion du gate de phase 4.

## Phases et gates

| Phase | Contenu | Gate de sortie |
| --- | --- | --- |
| 1 | Activer le service Compose `apps/hermes` (lecture seule) | UID 10000 / `CapEff` nul prouvés, coûts LiteLLM réels sous 20 EUR/mois |
| 2 | Gateway sur Talos, mêmes outils qu'en phase 1 | B1 : `bash scripts/talos/smoke-networkpolicy-enforcement.sh` vert (ingress et egress, autorisé et refusé, inter-nœuds) ; B2 résolu ; rollback testé |
| 3 | API interne, éventuelle gate PR par mention (webhook HMAC, rate limit) | Clés par client, aucun Ingress public hors chemin webhook |
| 4 | Broker + agent-sandbox, plugin sandbox seul outil d'exécution | Tests d'évasion : pas de token SA, egress refusé, TTL respecté, pas d'accès TrueNAS |

## Anti-patterns refusés

`terminal.backend: local` dans le pod qui détient les secrets, `NetworkPolicy`
désactivée, tag sans digest, installation de paquets au démarrage, dashboard
exposé publiquement, configuration modifiable depuis l'UI : chacun contredit
l'ADR Secure by Design et fait échouer les contrats de test.

## Rollback

Désinstaller la release Helm sans supprimer le PVC (`Retain`), révoquer bot
token, clé API et virtual key, revenir au service Compose ou à l'arrêt complet.
Ne jamais toucher aux namespaces CSI, Vault ou Falco pour un rollback Hermes.
