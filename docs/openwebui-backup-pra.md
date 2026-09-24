# OpenWebUI backup and disaster-recovery plan

## Scope

This runbook turns the provisional OpenWebUI Business Impact Analysis into a
testable backup and disaster-recovery capability.

The continuity service is **not** just the OpenWebUI container. The minimum
usable service requires:

1. OpenWebUI UI reachable from the LAN;
2. LiteLLM available as the model gateway;
3. OpenRAG backend available for the sensitive knowledge workflow;
4. one usable OpenAI-compatible GPU inference provider;
5. the required configuration and secrets restored.

Cloudflare Tunnel is a desired public-access path, but it is **not** part of the
minimum continuity objective because OpenWebUI remains usable from the LAN.

## BIA targets

| Objective | Target | Meaning |
| --- | --- | --- |
| Business criticality | high | Sensitive knowledge/configuration and required AI workflow |
| RTO | 1 day | Target time to restore the minimum usable service |
| Recovery escalation threshold | 3 days | Operator threshold to escalate to rebuild/alternate GPU capacity; this is stricter than the DMTP and is not a separate ISO BIA field |
| MTPD / DMTP | 7 days | Absolute maximum tolerable disruption |
| RPO | 1 day | Provisional objective until backup cadence and restore evidence prove it |
| Public Cloudflare path | non-blocking | Restore only after the LAN continuity path is green |

The current BIA remains `provisional` until the backup and restore exercises
below are accepted.

## Data classification and recovery priorities

OpenWebUI conversations can contain highly sensitive material retrieved from
OpenRAG. Prompt/history loss is acceptable within the reviewed RPO, but
confidentiality remains high.

Configuration is recovery-critical: a container that starts without the model,
RAG, authentication and security configuration is not an accepted recovery.

Recovery priority:

1. configuration, secret references and encryption/authentication material;
2. OpenRAG knowledge/configuration needed by the workflow;
3. OpenWebUI application state required for a functional UI;
4. recent conversation/prompt history within the RPO;
5. public Cloudflare access after LAN service acceptance.

## Backup set

### OpenWebUI

Primary persistent state currently mounted by Compose:

```text
/mnt/cpool/openwebui/data -> /app/backend/data
```

Back up the complete application-owned dataset/path rather than selecting
individual database files while the application is live.

OpenWebUI Pipelines currently uses the named Docker volume `pipelines`.
Before declaring the PRA complete, either:

- migrate pipeline content to a repository-owned/persistent bind mount; or
- include the named volume in the backup/restore procedure and prove its
  restoration.

### OpenRAG

The PRA must also preserve the OpenRAG state needed for the minimum service.
The Compose file currently persists relative paths for documents, keys, flow
backups, configuration and data.

Resolve their **actual TrueNAS runtime paths** from the deployed Compose working
directory before implementing backups; do not assume a path from repository
layout alone.

Sensitive OpenRAG documents/keys must be encrypted in any off-pool backup.

### LiteLLM and inference configuration

The LiteLLM declarative configuration is repository-managed. Runtime secrets
remain secret-manager/runtime material and must not be copied into Git or
plaintext backup manifests.

Recovery must prove the gateway can reach an OpenAI-compatible GPU inference
provider.

The logical catalog resource
`resource:default/gpu-openai-compatible-inference` deliberately does not bind
continuity to the current workstation. The current workstation may satisfy the
capability when powered on; a future cloud GPU provider should provide a
second implementation/fallback.

## Backup policy

To satisfy an RPO of one day with operational margin:

1. take local ZFS snapshots of the OpenWebUI application-owned dataset at least
   every **12 hours**;
2. keep enough local snapshots to cover at least 14 days of operator mistakes
   and application corruption;
3. create an **independent encrypted backup/replication off the primary pool at
   least daily**;
4. retain at least 30 daily recovery points initially;
5. protect encryption keys/credentials separately from the backed-up data;
6. monitor last-success timestamps and treat backup age greater than 24 hours
   as an RPO breach.

A snapshot on the same pool is a fast recovery point, **not** an independent
backup against pool/host loss.

The independent target is intentionally not selected by this document. Choose
and record one reviewed target before marking the backup control accepted
(second TrueNAS/pool, removable/offline storage, or encrypted remote/object
storage are possible implementations).

## Backup implementation preflight

When TrueNAS access is available, run the read-only repository diagnostic first:

```bash
sudo bash scripts/truenas/diagnose-openwebui-backup-pra.sh
sudo bash scripts/truenas/diagnose-openwebui-backup-pra.sh --check
```

The non-strict mode inventories/warns. `--check` fails when the one-day RPO is
not evidenced by current snapshots/independent backup state. The script does
not create snapshots, backup tasks or replication jobs.

Before creating schedules, identify the real storage owner:

```bash
findmnt -T /mnt/cpool/openwebui/data
zfs list -o name,mountpoint | grep -F '/mnt/cpool/openwebui'
```

Do not create or destroy datasets solely to make the runbook match an assumed
layout.

Also inventory the existing TrueNAS data-protection tasks before creating any
new schedule:

```bash
sudo midclt call pool.snapshottask.query | jq .
sudo midclt call replication.query | jq .
```

Do not create a duplicate task if an existing snapshot/replication policy
already covers the resolved dataset with an adequate cadence and retention.

Record:

- actual ZFS dataset;
- mountpoint;
- owner/group/mode;
- current data size;
- available space;
- last snapshot;
- chosen independent backup destination;
- encryption mechanism;
- backup scheduler/owner.

## Restore drill

Perform the first acceptance restore **without overwriting production data**.

1. Record incident/drill start time.
2. Select a recovery point no older than 24 hours.
3. Restore OpenWebUI data to an isolated temporary dataset/path.
4. Restore or materialize required configuration and secret references.
5. Restore/validate required OpenRAG persistent state.
6. Ensure the GPU inference capability is available:
   - power/validate the workstation provider when appropriate; or
   - select the reviewed alternate provider.
7. Start/validate LiteLLM.
8. Start/validate OpenRAG backend.
9. Start OpenWebUI against the restored state on an isolated LAN endpoint.
10. Validate:
    - UI login;
    - expected configuration/model visibility;
    - one LiteLLM-backed chat request;
    - one OpenRAG retrieval using non-destructive test content;
    - access through the LAN without Cloudflare;
    - no unexpected plaintext secret material in restored files/logs.
11. Record the achieved restore duration and recovery-point age.
12. Only after the LAN path is accepted, validate Cloudflare Tunnel/Access as a
    separate non-blocking public-access test.
13. Remove the temporary restore environment after evidence is archived.

## Recovery acceptance

The PRA is accepted only when all of the following are evidenced:

- restore duration <= 1 day (RTO);
- restored recovery point age <= 1 day (RPO);
- OpenWebUI UI is usable from the LAN;
- LiteLLM request succeeds;
- OpenRAG retrieval succeeds;
- a GPU-backed OpenAI-compatible inference request succeeds;
- critical configuration is present;
- sensitive data remains access-controlled/encrypted;
- Cloudflare failure does not block the LAN continuity path.

If recovery is not complete after 3 days, escalate to a full rebuild and/or
alternate GPU provider while preserving the 7-day DMTP as the absolute
business-continuity limit.

## Exercise cadence

Until the BIA is validated:

- review backup success at least weekly;
- run a non-destructive restore drill after initial implementation;
- repeat a restore drill at least quarterly;
- repeat after material changes to OpenWebUI storage, OpenRAG persistence,
  LiteLLM routing, secret materialization or GPU-provider architecture.

Once evidence is stable, the BIA owner may review whether the cadence can be
reduced.

## Evidence to retain

For every exercise retain:

- date and operator;
- source recovery point;
- backup age;
- restore start/end timestamps;
- achieved RTO;
- achieved RPO;
- restored dataset/path;
- OpenWebUI/LiteLLM/OpenRAG/GPU validation results;
- deviations;
- follow-up actions.

Never include secret values or sensitive conversation/document contents in the
evidence.
