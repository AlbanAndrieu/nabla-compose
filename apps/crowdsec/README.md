# CrowdSec

This deployment is the **central CrowdSec Security Engine + Local API (LAPI)** for the homelab.
pfSense should run in CrowdSec **Small / remediation-only** mode and consume decisions from this LAPI instead of hosting the Security Engine itself.

## Reprise du 27 octobre — GO/NO-GO avant pfSense Small

La migration n'est **pas réceptionnée** au dernier relevé :
la LAPI CrowdSec TrueNAS est saine, et Loki reçoit les événements
pfSense, mais la connexion du bouncer pfSense à cette LAPI
n'est pas démontrée. Le précédent bouncer utilisait
`http://172.17.0.1:8089` (LAPI locale) ; l'enregistrement
`PFSENSE_FIREWALL` côté central avait `last_pull=<none>`.
Le fichier privé
`/mnt/cpool/secrets/runtime/crowdsec/.env.secrets`
était alors absent/illisible. Aucun nouveau diagnostic CrowdSec
n'a été communiqué dans le relevé du 27/10 consacré à HAProxy.
**NE PAS arrêter le moteur local sur ces seules preuves.**

### Gate A — préflight TrueNAS en lecture seule

Sur **TrueNAS** (pas sur pfSense, sans afficher aucune clé) :

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --runtime
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --check
```

Critères : app RUNNING/healthy, LAPI LAN `:8084`, Loki pfSense
canonique confirmé, scénario de boucle désactivé ;
`--check` doit confirmer le fichier secret `0600`, la variable
`BOUNCER_KEY_PFSENSE_FIREWALL` et **exactement un** bouncer
`PFSENSE_FIREWALL`. Un `last_pull` vide est attendu avant
activation et doit être contrôlé après bascule ; il ne prouve
pas à lui seul une authentification préalable réussie.
Un échec de clé/secret est **NO-GO**. Ne jamais régénérer,
copier dans Git ou afficher la clé pendant un diagnostic.

### Gate B — préflight pfSense et authentification centrale

Depuis la **workstation**, avec l'accès SSH existant :

```bash
# En preflight, moteur local RUNNING = warning, pas échec.
just crowdsec-pfsense-preflight

# Probe authentifié de la LAPI centrale avec la clé du bouncer
# pfSense actuel. Lit la clé depuis sa configuration, sans l'afficher.
# Un HTTP 403 signifie que la clé actuelle appartient probablement
# à l'ancienne LAPI et ne peut pas servir au cutover telle quelle.
ssh -o BatchMode=yes -o ConnectTimeout=8 home.albandrieu.com sh -s \
  < scripts/pfsense/check-central-crowdsec-bouncer.sh
```

La probe doit retourner `central_lapi_http=200`. Si elle
retourne 401/403, **arrêter ici** : retrouver dans un coffre
approuvé la clé enregistrée sur TrueNAS, ou prévoir une rotation
explicite, séparée et réversible. Le préflight pfSense confirme
seulement l'état actuel des tables PF et l'accès réseau.

### Gate C — bascule contrôlée (opérateur, mutation hors du diagnostic)

Après A/B sans blocage et sauvegarde de la configuration pfSense :

1. Conserver les tables et la fonction firewall bouncer actives.
2. Faire pointer uniquement le bouncer pfSense vers
   `http://172.17.0.24:8084` avec **la clé centrale validée**.
3. Contrôler l'authentification, puis le `last_pull` réel
   dans `cscli bouncers list` sur TrueNAS.
4. Passer pfSense en mode Small : arrêter le **Security Engine**
   et ses traitements locaux, sans désactiver la remédiation PF.
5. Exécuter les réceptions **en lecture seule** :

   ```bash
   # TrueNAS
   sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --accept

   # workstation
   just crowdsec-pfsense-accept
   ```

6. Valider une décision non dangereuse réellement délivrée
   par la LAPI centrale et observée dans la table PF,
   puis son expiration/retrait. Ne jamais utiliser l'IP LAN
   de pfSense, TrueNAS ou de la workstation pour ce test.

**Rollback :** restaurer les paramètres bouncer/pfSense
préservés et vérifier les tables PF. Ne pas réactiver
automatiquement l'ancien moteur sans retirer le scénario
`firewallservices/pf-scan-multi_ports`, responsable
des boucles CPU historiques. Les scripts de diagnostic
et les recettes `just` sont **read-only** ; aucune bascule
pfSense ne s'exécute depuis cette PR.
## Target architecture

```text
pfSense RFC5424 ──> Alloy UDP/1514 ──> Loki ─┐
                                              ├──> CrowdSec Security Engine + LAPI on TrueNAS
Suricata eve.json ─────────────────────────────┘                  │
                                                  │ tcp/8084, LAN only
                                                  ▼
                                     pfSense firewall bouncer
                                                  │
                                                  ▼
                                            PF block tables
```

This removes CrowdSec parsing, scenarios, SQLite/LAPI work and CAPI synchronization from the resource-constrained pfSense appliance while keeping packet remediation at the firewall.

## Relevé opérateur — 26 octobre 2026 : bascule non autorisée

Les diagnostics ont été exécutés sans modification de service.
Le checkout TrueNAS affiche `head=de24ee7ae0cf`, `tree=dirty` :
éviter tout déploiement depuis cette copie avant revue de ses différences.

| Contrôle | Résultat observé |
| --- | --- |
| TrueNAS CrowdSec 1.8.1 | App RUNNING, conteneur running/healthy |
| LAPI TrueNAS `172.17.0.24:8084` | Listener OK ; `cscli lapi status` OK |
| Scénario `pf-scan-multi_ports` | Désactivé et fichier absent |
| Metrics `172.17.0.24:6060` | OK ; `cs_lokisource_hits_total=940` |
| Loki | `/ready=200`, query canonique `device=pfsense` **intermittente** (échec puis succès) |
| Décisions TrueNAS | `crowdsec_active_decisions=0` |
| Fichier secret bouncer TrueNAS | `/mnt/cpool/secrets/runtime/crowdsec/.env.secrets` absent ou illisible |
| Bouncer TrueNAS `PFSENSE_FIREWALL` | Inscrit, `last_pull=<none>` |
| pfSense Security Engine | Processus local **running** (pas Small) |
| pfSense firewall bouncer | **running**, URL `http://172.17.0.1:8089` (LAPI locale) |
| pfSense → TrueNAS LAPI | TCP `172.17.0.24:8084` joignable |
| Tables PF pfSense | `crowdsec_blacklists=9399`, `crowdsec6_blacklists=22` |

**Réception : BLOQUÉE.** La table PF à 9 421 entrées reflète
le bouncer encore relié à la **LAPI locale** ; elle ne démontre
aucune remédiation provenant de TrueNAS. Ne pas arrêter le moteur
local maintenant : ce serait un changement de la chaîne de protection
sans bouncer central fonctionnel ni rollback validé.

La requête Loki canonique a échoué lors de `--runtime` puis a
réussi lors de `--check`, alors que le compteur source valait 940.
Cela ne prouve pas une anomalie permanente de la règle Alloy.
Le diagnostic du dépôt fait désormais **une relance bornée** de
la requête exacte avant d'attribuer l'échec à la classification.
Une relance réussie conserve un warning ; deux échecs puis des
événements non-smoke provoquent un ERROR.

### Réception complémentaire : contrats et classification Loki

Le checkout de l'opérateur a exécuté sans erreur :

- `just crowdsec-loki-evidence-test` : **5/5 PASS** ;
- `just nexus-private-ingress-test` : **4/4 PASS**.

Depuis TrueNAS, la requête agrégée, sans lecture des messages :

```bash
curl --noproxy '*' -fsSG \
  'http://172.17.0.24:3100/loki/api/v1/query' \
  --data-urlencode \
  'query=sum by (device) (count_over_time({job="pfsense",app!="nabla-smoke"}[30m]))' |
  jq '.data.result | map({labels: .metric, count: .value[1]})'
```

retourne une unique série `{device="pfsense"}` avec **1 247
événements** sur la fenêtre de 30 minutes interrogée. Cela valide
la présence du label canonique dans ce relevé. Cela ne mesure ni
les événements totalement perdus avant Loki, ni l'absence de
microcoupures, ni une nouvelle décision CrowdSec.

**Conséquence opérationnelle :** aucune modification d'Alloy n'est
justifiée par l'échec ponctuel antérieur de la requête canonique.
La relance bornée du diagnostic signale une récupération, sans
transformer un échec persistant en succès. Les tests hors ligne
ne valident pas la configuration du bouncer pfSense, qui reste
connecté à la LAPI locale. Ne pas exécuter le cutover tant que
la clé centrale et `last_pull` ne sont pas confirmés.
### Séquence de décision avant la bascule

1. **Stabiliser les preuves** sur TrueNAS (lecture seule) :
   `sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --runtime`.
   En cas de warning Loki, interroger les compteurs/labels, sans
   modifier Alloy ni vider les journaux.
2. **Retrouver la clé centralisée existante** `PFSENSE_FIREWALL`
   dans une source approuvée. Contrôler les chemins/permissions
   sans afficher la valeur. Le `api_key` du bouncer qui parle à
   `172.17.0.1:8089` peut appartenir à **une autre LAPI** ;
   ne pas présumer qu'il correspond à la clé enregistrée sur TrueNAS.
   La présence d'une inscription `PFSENSE_FIREWALL` sans `last_pull`
   ne suffit pas à prouver la possession de sa clé.
3. **Ne provisionner le fichier** `root:root 0600`
   `/mnt/cpool/secrets/runtime/crowdsec/.env.secrets`
   que par un transfert approuvé, après vérification de l'identité
   et de l'absence de doublon. Aucune génération ou rotation de
   clé automatique.
4. **Exécuter `--check`** ; exiger zéro échec sur le secret,
   la classification Loki et l'enregistrement du bouncer.
5. **En fenêtre de migration approuvée**, faire pointer le seul
   bouncer pfSense vers `http://172.17.0.24:8084`, conserver
   sa remédiation active, retirer le moteur local, puis valider
   les deux `--accept` et le `last_pull` central.
   Préparer au préalable le retour à la configuration LAPI locale
   et documenter l'état des tables PF.

Le moteur TrueNAS fonctionne, mais **nous ne déclarons pas
la migration terminée** sans la preuve d'une décision centrale
réellement appliquée au niveau du pare-feu. Ne jamais tester
avec une IP de gestion critique ou introduire un ban factice
sans un plan de retour arrière.
## Current incident mitigation — 2026-10-10

The pfSense read-only diagnostic now proves the problematic path rather than
merely correlating it:

- Security Engine: stopped;
- firewall bouncer: still running;
- `crowdsec_pf_scan_stuck_lines=19213`;
- `max_failed_sent=19899999`;
- `max_attempts=19900000`;
- `max_sigclosed=0`.

That shape is consistent with a live leaky bucket whose input cannot accept the
event, causing the producer to busy-spin. CrowdSec upstream issue
[crowdsecurity/crowdsec#1519](https://github.com/crowdsecurity/crowdsec/issues/1519)
describes the same tight-loop failure mode. The current CrowdSec 1.8.1 source
still contains the non-blocking retry path, so upgrading alone is not treated as
a fix.

The central TrueNAS engine is therefore pinned to CrowdSec 1.8.1 **and**
temporarily removes only the offending Hub scenario through the official
container variable:

```text
DISABLE_SCENARIOS=firewallservices/pf-scan-multi_ports
```

The rest of `crowdsecurity/pfsense` remains installed. Do not re-enable the
pfSense Security Engine while this incident is open merely to regain this one
port-scan scenario.

## Runtime variables

The central engine can bootstrap without a bouncer secret. The optional
`/mnt/cpool/secrets/runtime/crowdsec/.env.secrets` file is loaded only when present, so a
missing secret file no longer makes the entire TrueNAS Compose model invalid.

The **TrueNAS runtime pool** is the service's operative secret source:
`/mnt/cpool/secrets/runtime/crowdsec/.env.secrets`. CrowdSec never needs
Vaultwarden to start, restart, redeploy or recover after an outage. The file is
optional during engine bootstrap but **required before accepting the pfSense
bouncer cutover**. A missing file is not proof that the engine itself is down.

Vaultwarden is an **optional operator-managed vault and recovery copy**, not
a mandatory live dependency or a prerequisite for an already-populated runtime
secret. Neither Compose nor the CrowdSec deployment/diagnostic scripts connect
to Vaultwarden to obtain the key. Preserve the runtime materialization on ZFS
with a separately controlled backup and recovery plan, especially while
Vaultwarden is offline.

### Complete the runtime-pool migration first

1. Confirm the local runtime path, restrictive permissions and presence of
   `BOUNCER_KEY_PFSENSE_FIREWALL` using the **read-only** diagnostic; never
   print the value or source the dotenv into the operator's shell.
2. If absent, restore or transfer the **previously issued bouncer key** into
   a private file through an approved, audited operator process. Optionally
   retrieve it from Vaultwarden if it exists there, but do not make this
   mandatory and do not invent or rotate it automatically.
3. Install the reviewed material into
   `/mnt/cpool/secrets/runtime/crowdsec/.env.secrets` with `root:root 0600`
   and directory `0700`. Avoid storing staging copies in shared `/tmp` or
   the Git checkout. The runtime file is an operating asset, not a Git artifact.
4. Run the read-only `--check` acceptance. Only then perform an explicitly
   authorized CrowdSec redeploy and pfSense bouncer reconfiguration from the
   workstation's existing administrative boundary.

The runtime file is the contract: it must define the container-facing
`BOUNCER_KEY_PFSENSE_FIREWALL`. The inventory manifest's legacy
`CROWDSEC_PFSENSE_BOUNCER_KEY` alias applies **only when importing** a secret
from the optional vault workflow. A registered CrowdSec bouncer does not
reveal its existing API key; if the key cannot be recovered, an explicitly
reviewed rotation is required, not an automated silent replacement.

```bash
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --runtime
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --check
# After a reviewed cutover, run --accept
```

Keep the pfSense-side verification separate: the workstation must acquire
the same credential via an approved provisioning channel, which may be the
vault or a controlled transfer. Never automatically copy a TrueNAS runtime
secret to the workstation, print it, pass it as a CLI argument, or grant TrueNAS
administrative SSH/API access to pfSense.

#### Optional vault backup or materialization (not a runtime prerequisite)

When Vaultwarden **is available**, the unprivileged operator may maintain a
recoverable copy with `scripts/secrets/materialize_runtime.py`, following
`docs/secrets-runtime-initialization.md`. If the CrowdSec item is missing in
the vault, **do not overwrite or remove the existing valid runtime file**.
Do not use the vault import as proof of the running bouncer identity; validate
the identity and cutover separately. Bitwarden CLI compatibility is relevant
only for this optional vault interaction, not normal CrowdSec operation.

Optional:

```text
CROWDSEC_LAPI_BIND_ADDRESS=172.17.0.24
CROWDSEC_LAPI_PORT=8084
CROWDSEC_METRICS_BIND_ADDRESS=172.17.0.24
CROWDSEC_METRICS_PORT=6060
SURICATA_LOG_DIR=/mnt/cpool/suricata/log
TZ=Europe/Paris
```

The LAPI port must remain reachable from trusted LAN hosts only. Do not publish TCP/8084 through pfSense, Cloudflare Tunnel, HAProxy or any Internet-facing ingress.

## TrueNAS Custom App deployment

The app may be installed before the bouncer secret exists. For the final
pfSense cutover, confirm the approved key is already materialized in
`/mnt/cpool/secrets/runtime/crowdsec/.env.secrets` before the controlled redeploy.
Register the missing Custom App with the canonical repository include:

```bash
CROWDSEC_WRAPPER="$(
  cat <<'EOF'
include:
  - /mnt/cpool/compose/nabla-compose/apps/crowdsec/compose.yml
EOF
)"

sudo midclt call -j app.create "$(
  jq -cn \
    --arg compose "${CROWDSEC_WRAPPER}" \
    '{
      app_name: "crowdsec",
      custom_app: true,
      custom_compose_config_string: $compose
    }'
)"
```

Use `app.redeploy crowdsec` only after `app.query` confirms the app exists.

Before changing pfSense, use the scoped repository deployer. Its default mode is
read-only. A missing bouncer credential is reported as a **cutover warning**,
not as a blocker for repairing the central TrueNAS runtime. Uncommitted changes
inside the CrowdSec deployment scope remain a blocking precondition.

```bash
sudo bash scripts/truenas/deploy-crowdsec.sh --check
sudo bash scripts/truenas/deploy-crowdsec.sh --apply
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --runtime

# Only after the canonical bouncer credential is materialized:
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --check
```

`--apply` reconciles **only** the TrueNAS CrowdSec Custom App; it does not
change pfSense, create/delete a bouncer, rotate a key or start the local pfSense
Security Engine. The post-reconcile `--runtime` gate proves the image, scenario
exclusion, LAPI/listeners and Loki acquisition independently from cutover
credentials.

The stronger `--check` gate additionally verifies the canonical bouncer-secret
contract and central `PFSENSE_FIREWALL` registration. It never creates a
bouncer, prints a key, redeploys an App or restarts a service.

After pfSense is switched to the remote LAPI, require the stronger acceptance
gate:

```bash
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --accept
```

`--accept` additionally requires that the pfSense firewall bouncer has polled
the central LAPI at least once.

The acceptance is intentionally split by trust boundary:

**On TrueNAS only** — validate the central engine/LAPI/Loki path and observe
`crowdsec_active_decisions`:

```bash
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --check
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --accept
```

TrueNAS never SSHes to pfSense.

**On the workstation only** — run the pre-cutover gate over the workstation's
existing SSH path. This checks that pfSense can reach the TrueNAS LAPI without
requiring the bouncer to have switched yet:

```bash
bash scripts/workstation/verify-crowdsec-pfsense.sh --preflight
```

The current legacy URL `http://172.17.0.1:8089` is a warning in preflight
mode. After changing the CrowdSec package settings, use the strict gate:

```bash
bash scripts/workstation/verify-crowdsec-pfsense.sh --accept
```

It verifies that the local Security Engine is absent, the firewall bouncer is
running, its `api_url` targets `http://172.17.0.24:8084`, and the
`crowdsec_blacklists` / `crowdsec6_blacklists` PF tables exist. Empty tables
are a warning by default because they are legitimate when no active ban exists.
When the TrueNAS diagnostic reports `crowdsec_active_decisions>0`, rerun the
workstation helper with `--require-nonempty-table`; an empty PF table then
becomes a failure. Do not run `docker exec` from the workstation.

## Migration from pfSense Large to Small

1. Keep the existing pfSense **firewall bouncer** running, but keep the local
   Security Engine stopped while the backpressure incident remains open.
2. Deploy the central TrueNAS CrowdSec container and verify that
   `firewallservices/pf-scan-multi_ports` is absent while the remaining
   `crowdsecurity/pfsense` collection is installed.
3. Recover the **existing approved** `PFSENSE_FIREWALL` bouncer key from an
   operator-controlled source, store it as the manifest field
   `CROWDSEC_PFSENSE_BOUNCER_KEY`, then materialize it for TrueNAS. If the key
   cannot be recovered, stop: creating/rotating a bouncer key is a separate
   explicitly approved transaction, not part of this cutover.
4. Run `diagnose-crowdsec-cutover.sh --check`; require zero failures before
   touching pfSense.
5. From pfSense, verify that `172.17.0.24:8084` is reachable over the trusted LAN.
6. In **Services > CrowdSec** on pfSense:
   - keep **Remediation Component** enabled;
   - keep **Log Processor** disabled;
   - keep **Local API** disabled;
   - configure the remote LAPI URL as `http://172.17.0.24:8084`;
   - configure the firewall bouncer with the shared key.
7. Save/apply, then run `diagnose-crowdsec-cutover.sh --accept` on TrueNAS and
   require a non-empty `last_pull` for `PFSENSE_FIREWALL`.
8. Confirm that pfSense still receives CrowdSec decisions in its PF table before
   considering the migration complete.

Rollback the **cutover**, not the incident mitigation: restore the previous
bouncer/LAPI settings from the backed-up pfSense configuration, but do not
automatically re-enable the local Security Engine. An emergency local-engine
rollback must first exclude `firewallservices/pf-scan-multi_ports` and must be
observed with bounded CPU/RSS and free-memory headroom.

## Detection sources

The central engine currently acquires:

- pfSense RFC5424 events from the **existing Loki stream**
  `{job="pfsense", device="pfsense"}`, produced by Alloy on TrueNAS;
- Suricata `eve.json` from `${SURICATA_LOG_DIR}`.

This intentionally avoids a second syslog receiver and avoids inventing a
`/mnt/cpool/logs/pfsense/*.log` persistence path that the observability stack
does not create. CrowdSec's Loki datasource starts at the current time, so
post-redeploy acceptance must generate/observe fresh pfSense activity.

The pfSense logs are parsed centrally on TrueNAS after migration, so pfSense
Small mode does not need to run the CrowdSec Log Processor.

## Motivation and current pfSense evidence

Before migration, pfSense CrowdSec was the dominant CPU consumer. `filter.log` generated a very high parse workload compared with useful events, and `firewallservices/pf-scan-multi_ports` repeatedly reported event-delivery backpressure with millions of failed send attempts. The firewall bouncer itself remained healthy and inexpensive, so the remediation component should stay on pfSense while the Security Engine/LAPI moves here.

## Validation after cutover

On TrueNAS:

```sh
docker exec crowdsec cscli metrics
docker exec crowdsec cscli decisions list
docker exec crowdsec cscli bouncers list
```

On pfSense:

```sh
pfctl -T show -t crowdsec_blacklists | head
ps auxww | grep -Ei '[c]rowdsec|[c]rowdsec-firewall-bouncer'
uptime
```

Expected result: the firewall bouncer continues polling and populating PF tables, while the `crowdsec` Security Engine process no longer runs locally on pfSense.

## pfSense tcsh-safe central LAPI authentication probe

pfSense admin's interactive shell is `tcsh`, not POSIX `sh`.
Never paste shell assignments such as `KEY=$(...)` directly into that
prompt. Use the repository script through an explicitly selected
POSIX interpreter **from the workstation checkout**:

```bash
ssh -T home.albandrieu.com 'sudo /bin/sh -s' < scripts/pfsense/check-central-crowdsec-bouncer.sh
```

The script reads the existing pfSense bouncer key locally, does **not**
print it or include it in curl argv, and reports only
`central_lapi_http=200` (authenticated) or a safe error/status.
It sends one GET for test address `192.0.2.1`, does not change
firewall configuration or PF tables, and may update LAPI polling
metadata. Run only on trusted pfSense via the workstation's authenticated
SSH channel. A 401/403 means the key is not accepted; do not infer
matching credentials from the names `pfsense-firewall` and
`PFSENSE_FIREWALL`.
