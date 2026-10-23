# FastAPI Sample · TrueNAS staging deployment and bounded diagnostics

Scope: operator-run procedures for `sample` on TrueNAS. Does not change
FastAPI Cloud or Cloudflare policies. The stage endpoint is
`http://127.0.0.1:8091` from TrueNAS.

## Incident DNS/ECH Sample (23 octobre 2026)

Le [dossier d'incident](../incidents/2026-10-23-sample-pihole-ech-split-dns.md)
compare les incidents du 27 septembre (DHCP vers Pi-hole), du 10 octobre
(Vaultwarden Unbound public override), et l'incident actuel : **Pi-hole v6**
a une entrée `172.17.0.24 sample.albandrieu.com` dans `pihole.toml`.
Le DHCP LAN pfSense annonce déjà **172.17.0.1**, donc ne pas le modifier.

Sur TrueNAS, `diagnose-fastapi-sample.sh` ajoute une septième étape
pour le DNS, sans redémarrage ni affichage de secrets :

```bash
cd /mnt/cpool/compose/nabla-compose
just sample-dns-truenas
bash scripts/truenas/diagnose-fastapi-sample.sh --cycles 1 --color never
```

Depuis une **workstation Linux** (`eno1` par défaut) :

```bash
just sample-dns-workstation
# ou, sans just :
bash scripts/ingress/diagnose-sample-dns.sh --workstation

# Pour savoir d'où provient Quad9 malgré le DHCP pfSense :
nmcli -t -f NAME,DEVICE connection show --active
nmcli -f DHCP4.OPTION device show eno1 |
  grep -Ei 'domain_name_servers|dhcp_server_identifier'
resolvectl dns eno1
```

`just sample-dns-test` vérifie le diagnostic en local avec des faux DNS,
Docker, NetworkManager et systemd ; aucune CI payante. Le contrôle Pi-hole
inspecte uniquement la présence du hostname public dans les fichiers
connus et n'en affiche jamais le contenu. La correction de `pihole.toml`
doit être réalisée par la configuration gérée de Pi-hole après revue,
sans effacer le hostname privé `sample.int.albandrieu.com`.

**Interprétation des retours du 23 octobre :** une sortie `just sample-dns`
avec `failures=1` reste un échec attendu tant que Pi-hole répond par
`172.17.0.24` pour le hostname public ; ne pas convertir ce FAIL
en PASS silencieux. `pihole_override_source` est une preuve de
provenance, pas un second incident comptabilisé. Depuis une workstation,
l'inspection du conteneur Pi-hole distant est `SKIP`, pas un WARN de
l'application ; la requête DNS vers Pi-hole fonctionne malgré ce SKIP.

`just sample-dns` vérifie le DNS sur tout hôte **sans introspection Docker locale** ;
`just sample-dns-truenas` exige explicitement TrueNAS et inspecte Pi-hole en lecture seule.
Un WARN Docker sur un poste Linux qui n'héberge pas Pi-hole n'est plus attendu.

`just sample-dns-workstation` lit désormais les propriétés
`ipv4.dns`, `ipv4.ignore-auto-dns`, `ipv4.dns-priority` et
`ipv4.dns-search` du **profil NetworkManager actif**, sans secrets.
Elle vérifie également `getent ahostsv4 sample.int.albandrieu.com`
pour éviter qu'un DNS Quad9 public cache une régression sur la zone
privée. Les cas mockés ont été portés à **8 tests**, incluant une réponse DNS NetworkManager vide (code de sortie zéro) et les modes TrueNAS/workstation (exécution du
nouveau HEAD : `NOT_RUN`). Voir le dossier d'incident pour les
étapes de remédiation sous Pi-hole v6.

Une réponse **HTTP 302** vers Cloudflare Access sans session est attendue
après correction DNS ; elle ne prouve pas la santé du backend ni un échec TLS.

## What the 2026-10-17 results show

- The unqualified command `sudo bash scripts/truenas/update-fastapi-sample.sh`
  deployed **`master` `8c4492d131c3ec6e0c0e4cdc18f261c0b9af40d4`**,
  not unmerged fastapi-sample PR #342 `748497d62881f7631801c8f8cd11bbf4c04633e8`.
- Staging reports `healthy`, `v0+1.22.1`, TrueNAS observer access
  3/3 and pfSense least-privilege 7/7. Gatus was up with 78 synthetic series.
- The parent Git repository pins submodule `f8ecc776...`; its working
  checkout is now `8c4492d1...`. The resulting `M fastapi-sample` in
  the parent is expected Gitlink drift, **not proof of modified Python code**.
  Do not automatically stage or commit that Gitlink during a staged test.
- For public HTTP endpoints, TrueNAS-host requests completed in
  0.09/0.10/0.54 seconds; container requests in 0.45/0.44/0.64 seconds.
  Container DNS: 0.04–0.19 seconds. These samples do **not** show a sustained
  DNS/egress outage. They also do not prove the 12 concurrent public probes
  fit in the existing 4-second fan-out budget. Keep that budget unchanged
  until repeated service-specific timings identify the bottleneck.
- Garage HTTP 302 is an Access/edge response, not proof of anonymous
  Garage origin access or application health.

## Compact deployment output

The updater now groups steps into six stages and summarizes:
- requested ref and checkout SHA; **default `master` is explicit**;
- Docker build mode, service health and application version;
- observer network, TrueNAS allowlist, Gatus and pfSense RBAC;
- expected Gitlink mismatch, plus `build_revision=null` evidence limitation.

Routine Git fetch/submodule chatter, network JSON, full health payload and
authenticated pfSense smoke stdout are suppressed on success. A failed
operation retains a bounded diagnostic excerpt. For intentionally verbose
build output only, set `FASTAPI_SAMPLE_VERBOSE_LOGS=true`. Do not publish
unredacted verbose logs.

**Safety:** `update-fastapi-sample.sh` is NOT read-only. It builds images,
may reconcile observer allowlists, replaces the staging container and runs
TrueNAS app.update/redeploy. Confirm reviewed ref and rollback state first.

## Terminal UI, shared formatting, and diagnostic interpretation

The shell-only helper `scripts/lib/diagnostic-ui.sh` is shared by the
FastAPI, Gatus and resource-usage diagnostics. It makes WARN / FAIL / UNKNOWN
visually distinct from connectivity and HTTP evidence. No Docker or network
operations live in this helper.

The FastAPI diagnostic accepts `--color auto|always|never` and
`--icons auto|always|never` (auto by default).
- Auto colors are active only on a TTY; a normal tee pipe receives clean,
  color-free diagnostic output.
- `NO_COLOR` disables ANSI coloring in all modes, including forced color.
- Icons require a UTF-8 locale in auto mode, but can be forced or disabled.
- `--expected-sha` is a full 40-character Git commit expectation;
  discrepancies are warnings and **never** cause deployment.

Plain output to the operational log:

```bash
set -o pipefail
bash scripts/truenas/diagnose-fastapi-sample.sh --cycles 3 --color never \
  | tee "/tmp/fastapi-sample-diagnostic-$(date +%Y%m%d-%H%M%S).log"
```

For colored terminal output with a plain log, while connected to an
interactive SSH terminal:

```bash
set -o pipefail
LOG="/tmp/fastapi-sample-diagnostic-$(date +%Y%m%d-%H%M%S).log"
bash scripts/truenas/diagnose-fastapi-sample.sh \
  --cycles 3 --color always --icons always \
  | tee /dev/tty \
  | sed -E 's/\x1B\[[0-9;]*[[:alpha:]]//g' > "$LOG"
```

The terminal shows colored status labels while the log is ANSI-free. Do
not use `/dev/tty` in headless automation; use the plain command instead.

The October 17 staging evidence is:

- FastAPI checkout and parent Gitlink were both 8c4492d1 (master), not PR
  #342; build_revision was null, so version 1.22.1 is not exact-source proof.
- Local LanguageTool catalog reported one entry (earlier duplicate resolved
  locally); three Garage entries lacked probePriority and deploymentUnitId.
- Internal probe completion was 12, but only Garage Admin appeared in its
  internal-service evidence. Public probes returned completed=2, timed_out=10
  over two successful cycles; the first cycle was unavailable/unknown.
- Docker-container public HTTP probes were 0.28-0.61 s end-to-end, with
  fast DNS. These results **do not prove** a DNS problem; they warrant
  correlated measurement of the 4 s aggregate fan-out deadline.
- Prometheus /-/ready responded, but the metric query yielded only
  nabla:telemetry:gatus_up. Missing current series are UNKNOWN telemetry
  until their recording rules and scrape targets are verified.

## Required acceptance after publishing these scripts

- [ ] Verify shell syntax, local mock contracts and pre-commit rules on the
  exact nabla-compose PR head.
- [ ] Rerun read-only diagnostics on TrueNAS; check that warnings describe
  actual missing evidence and colors do not enter ordinary logs.
- [ ] Confirm FastAPI PR #342 runtime explicitly on staging before using
  the full 3/3 Garage acceptance gate; do not conflate running master with
  testing an unmerged PR.
- [ ] No restart, configuration mutation, automatic CI rerun or merge.

### Latest operator diagnostic (2026-10-17)

The operator's newest three-cycle run shows public completed/timed-out
`9/3`, `1/11`, `1/11` and Garage LAN endpoint coverage `3/3`,
`2/3`, `2/3`; this variability needs probe scheduling/cache-budget
attribution, not blind DNS changes or inflated timeouts. Host and container
HTTP edge requests remain individually subsecond. The locally inspected
LanguageTool catalog contains one entry, but live consumer provenance is
not independently proven. Three expected Prometheus synthetic recording
families were absent from the instant-query result while `gatus_up=1`.
The FastAPI staging checkout is still `master` `8c4492d1`, **not**
the unmerged PR #342; do not consider its three-Garage regression accepted.

## Non-destructive diagnostic

After updating the `nabla-compose` PR branch, run as its regular
repository owner (avoid running Git as root):

```bash
cd /mnt/cpool/compose/nabla-compose
git pull --ff-only origin feat/watchtower-zero-trust-service-units-20261016
bash scripts/truenas/diagnose-fastapi-sample.sh --cycles 3
```

The existing `M fastapi-sample` Gitlink may remain after this fast-forward.
Do not reset it or automatically stage it just to silence `git status`.
If the fast-forward refuses due to unrelated local changes, resolve that
state separately before using the updated script. **Do not run `sudo -v`.**
A sudo password is neither needed nor requested for read-only diagnostics.
Docker and `midclt` are tried directly first; if permission is missing,
the script tries narrowly scoped `sudo -n` (non-interactive) and reports
unavailable evidence if permission is not granted. Never paste a password or
change sudoers just to run this diagnostic. Note that direct Docker access is
privileged and effectively grants powerful control of the host.

Option `--cycles 1` is a quick check; `--cycles 3` samples cached
`/api/health-board` at 31-second intervals (two waits). Option
`--interval 30..120` changes only that sampling interval. Each external
request uses no redirect following and a 12-second maximum; the
health-board is bounded to 30 seconds/cycle.

The diagnostic collects:
1. parent/submodule SHAs (Git commands executed as the repository owner),
   TrueNAS app and Docker state, runtime `/v2/version`, and a sanitized
   count of LanguageTool/ Garage records in the canonical catalog;
2. the same three public HTTP timing probes from TrueNAS and inside Docker;
3. sanitized Docker resolver metadata (no environment dump);
4. internal/public health-board summary plus Garage member evidence;
5. Prometheus `/-/ready` and bounded Gatus synthetic series counts;
6. one Docker stats snapshot.

Nothing is restarted, no secrets or response headers are emitted, no
Cloudflare Access login URL is followed. Redact environment-specific hostnames
and service details before publishing outside the operational team.

### Testing the specific FastAPI PR (requires explicit operator approval)

Use explicit `sudo env` so the requested ref is passed to the root-run helper without inheriting unrelated shell environment variables:

```bash
sudo env FASTAPI_SAMPLE_DEPLOY_MODE=build \
  FASTAPI_SAMPLE_REF=748497d62881f7631801c8f8cd11bbf4c04633e8 \
  bash scripts/truenas/update-fastapi-sample.sh
```

**Do not run this command just for diagnostic collection**; it changes the
staging runtime. Confirm no tracked edits inside `fastapi-sample`, staged
runtime secrets, and an accepted rollback SHA/image. After deployment, rerun
`diagnose-fastapi-sample.sh --cycles 3` and verify Garage internal probes,
`priority_source`, public completed/timed_out and any Cloudflare tunnel
warning. If the health board still reports `timed_out=12` but individual
HTTP requests remain fast, investigate scheduling/concurrency, other
endpoints and cold-vs-warm cache rather than adjusting DNS or inflating
timeouts without evidence.

Note: `/v2/version.build_revision=null` cannot attest running image SHA.
The updater's Git checkout SHA is provenance for the local *build context*,
not cryptographic attestation of the deployed image. An OCI revision label or
immutable image digest attestation is a separate follow-up.

## Follow-up acceptance

- [ ] Current fastapi-sample PR revision deployed intentionally on staging.
- [ ] Three health-board cycles show all Garage components with fresh LAN
      evidence and correct `external`/exposure intent.
- [ ] Public timeout rate and endpoint timings correlated with resource use.
- [ ] Authoritative `nabla-compose` catalog fixes LanguageTool duplicate;
      FastAPI successfully consumes canonical priority metadata.
- [ ] Full repo quality gate and deployment script validation at exact HEAD;
      no unnecessary GitHub Actions dispatch. Never merge automatically.
