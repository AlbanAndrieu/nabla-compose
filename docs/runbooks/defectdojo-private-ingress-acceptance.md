# DefectDojo private ingress — acceptance after PR #257

This runbook follows merged PR #257. DefectDojo's Nginx frontend is configured for the internal hostname `defectdojo.int.albandrieu.com` on Traefik `websecure`; public Cloudflare DNS, AutoXpose and WAN HAProxy are **not** part of the intended path.

## Priorité runtime — interface privée indisponible (24 octobre 2026)

L'opérateur constate que `https://defectdojo.int.albandrieu.com/`
ne répond pas. La cause n'est **pas encore établie** : navigateur/DNS privé,
TLS de Traefik, service Nginx, Django/uWSGI ou PostgreSQL.
Le dernier HTTP 403 observé historiquement sur `/api/v2/` prouve
uniquement que l'API refusait une requête anonyme ; cela ne garantit pas
la page HTML de connexion.

Sur un shell **TrueNAS**, depuis le checkout canonique contenant le
diagnostic actuel (ou après revue de la PR Draft #274) :

```bash
sudo bash scripts/truenas/preflight-defectdojo.sh
sudo bash scripts/truenas/diagnose-defectdojo.sh --check
```

Le diagnostic est strictement en lecture seule et sépare :

| Couche | Observation | Interprétation |
| --- | --- | --- |
| Docker | `defectdojo`, `defectdojo-uwsgi`, `traefik` en cours d'exécution | Présence, sans garantir la réponse Django |
| TCP/HTTP LAN | `http://172.17.0.24:31085/api/v2/` | HTTP 403 attendu pour API anonyme |
| UI locale | `http://172.17.0.24:31085/` | HTTP 200 ou redirection 30x = frontend accessible ; 000/404/5xx = panne |
| DNS interne | Pi-hole `172.17.0.24` et pfSense `172.17.0.1` | doivent résoudre la cible privée |
| DNS public | `1.1.1.1` | aucune publication publique voulue |
| HTTPS privé | `curl --resolve` avec vérification TLS/SNI | doit joindre le routeur Traefik correspondant |

Un résultat `ui_origin_http=000` avec `api_http=403` signale
`api_reachable_but_ui_origin_unavailable`. Si l'UI LAN fonctionne mais
`https_http=000`, vérifier DNS/SNI et le certificat Traefik plutôt que
de modifier Django. Un 404 sur Traefik peut indiquer un routeur absent.
Aucune hypothèse ne justifie un reset de la base.

La route privée ne doit pas être exposée publiquement. Conserver
PostgreSQL, Redis, les données d'audit et les secrets de chiffrement.
Le compte Django `admin` était le seul utilisateur observé dans
l'inventaire du 23 octobre ; la rotation de son mot de passe est un
**chantier séparé**, à effectuer uniquement en mode TTY interactif
et avec synchronisation Vaultwarden, une fois l'interface joignable.

## Execution order

1. Ensure the branch is based on the current `master`. Preserve any dirty working tree; do not reset unrelated changes.
2. Regenerate `catalog/service-topology.json` with `python3 scripts/generate-service-topology.py`, inspect the diff, and commit generated outputs through the local-first quality gate.
3. Run `sudo docker compose -f apps/defectdojo/compose.yml config --quiet --no-interpolate --no-env-resolution` and `sudo bash scripts/truenas/deploy-security-tooling.sh --check defectdojo`; do not deploy while either fails.
4. In a controlled runtime window, deploy using `sudo bash scripts/truenas/deploy-security-tooling.sh --apply defectdojo`.
5. Verify DNS independently at Pi-hole and Unbound, then HTTPS directly to Traefik with SNI. Check that the hostname has **no public DNS record**.

## Read-only verification

```bash
dig +noall +comments +answer +authority @172.17.0.24 defectdojo.int.albandrieu.com A
dig +noall +comments +answer +authority @172.17.0.1 defectdojo.int.albandrieu.com A
dig +short @172.17.0.24 hello.int.albandrieu.com A
dig +short @172.17.0.1 hello.int.albandrieu.com A
sudo bash scripts/truenas/diagnose-defectdojo.sh --check
sudo docker inspect defectdojo --format '{{json .NetworkSettings.Networks}}' | jq 'keys'
curl -sS -D - -o /dev/null --max-time 10 \
  --resolve defectdojo.int.albandrieu.com:443:172.17.0.24 \
  https://defectdojo.int.albandrieu.com/
dig +short @1.1.1.1 defectdojo.int.albandrieu.com A
```

Expected: Pi-hole and Unbound both resolve the private name to `172.17.0.24`; the public resolver has no A record; Traefik returns a valid TLS response and a login redirect. A `404` from direct Traefik without Host/SNI is expected and does not test the intended router.

## Known observations

On October 17, 2026, Pi-hole returned `172.17.0.24` for Hello but no A answer for DefectDojo; pfSense/Unbound returned the public `82.66.4.247` for Hello; `pihole-dns-sync` was healthy (historical restart count 1); DefectDojo's frontend was on the `intranet` network prior to applying the merged Traefik change. The `--check` gate failed because `catalog/service-topology.json` was stale.

The DNS discrepancy requires independent diagnosis. Do not introduce a per-service pfSense Host Override unless the documented delegated-zone architecture is deliberately changed. Do not expose DefectDojo as a Hello-style public canary. No runtime acceptance is claimed by this document.

## LAN API bind and importer contract (follow-up to PR #258)

Operator observations: Docker publishes `172.17.0.24:31085` (not `127.0.0.1:31085`); unauthenticated `GET http://172.17.0.24:31085/api/v2/` returned HTTP 403; `defectdojo.int.albandrieu.com` was unresolved through the default resolver. HTTP 403 confirms a reachable HTTP endpoint, **not** a successful authenticated API call. No public exposure has been validated.

The scan importer now uses the fixed TrueNAS LAN binding `http://172.17.0.24:31085/api/v2/reimport-scan/`. The existing host checkout requirement is supplemented by a local-interface check for `172.17.0.24` prior to reading credentials or sending the scan. The endpoint is not configurable, the importer disables proxies, redirects and HTTPS downgrade/fallback, and the apply path still requires root, explicit approval and the protected token file.

Read-only checks before first import:

```bash
sudo ss -ltnp | grep ':31085'
curl --noproxy '*' --max-time 5 -sS -o /dev/null -w 'HTTP %{http_code}\n' http://172.17.0.24:31085/api/v2/
dig +short @172.17.0.24 defectdojo.int.albandrieu.com A
dig +short @172.17.0.1 defectdojo.int.albandrieu.com A
dig +short @1.1.1.1 defectdojo.int.albandrieu.com A
```

Resolve the private DNS via the canonical Pi-hole sync -> Unbound pathway; do not create an unreviewed public DNS or Cloudflare Tunnel route. Validate LAN firewall and inter-VLAN restrictions separately, as binding to an RFC1918 address does not constitute an access-control policy. Do not perform `--apply` until the authenticated endpoint, parser and engagement are approved.

## TrueNAS preflight accepted, DNS still pending (operator evidence)

On the current PR branch, `bash scripts/agent-quality-gate.sh --preflight` passed all Git-only checks including the destructive-diff guard. `br0` owns `172.17.0.24/24`, Docker publishes `8080/tcp -> 172.17.0.24:31085`, and unauthenticated `GET /api/v2/` returned HTTP 403. Queries against Pi-hole `172.17.0.24`, Unbound `172.17.0.1`, and public `1.1.1.1` produced no A records for the private DefectDojo name. These observations do **not** establish HTTPS, API authorization or firewall policy acceptance.

Next perform read-only diagnostics, preserving DNS server response codes (NXDOMAIN versus NOERROR/NODATA) and Traefik router status:

```bash
for dns in 172.17.0.24 172.17.0.1 1.1.1.1; do
  echo "== DNS ${dns} =="
  dig +time=2 +tries=1 +noall +comments +answer +authority @"${dns}" defectdojo.int.albandrieu.com A
done
sudo docker inspect defectdojo --format '{{json .NetworkSettings.Networks}}' | jq 'keys'
sudo docker inspect traefik --format '{{json .NetworkSettings.Networks}}' | jq 'keys'
curl --noproxy '*' -sS -D - -o /dev/null --max-time 10 \
  --resolve defectdojo.int.albandrieu.com:443:172.17.0.24 \
  https://defectdojo.int.albandrieu.com/
```

Do not use `curl -k` for acceptance. A missing DNS A record should be corrected in the existing label-driven Pi-hole sync path, after confirming the sync's container selection, labels and successful reconciliation. Do not create an unrelated pfSense override or public record. The `--apply` importer remains gated on approved authenticated API validation and a reviewed scan report.

## Unified read-only diagnostic

Run `sudo bash scripts/truenas/diagnose-defectdojo.sh --check` on TrueNAS. It checks the local interface, Docker networks and published port, unauthenticated HTTP reachability, internal/public DNS A answers, and verified HTTPS with SNI. It does not query API tokens, retrieve application logs, modify containers or create DNS records. Nonzero exit means at least one acceptance failure. No restart or deployment is performed automatically.

Observed failure baseline: `defectdojo` has only `intranet`, while `traefik` has `traefik_network`; both internal DNS resolvers returned NOERROR/NODATA and public DNS had no A record; HTTPS SNI returned 404. Reconcile the declared `traefik_network` attachment through an approved TrueNAS app deployment and fix Pi-hole sync before considering the service accepted. Preserve LAN-only publication and do not create a public route.

## Runtime acceptance update — October 17, 2026

The operator ran `sudo bash scripts/truenas/deploy-security-tooling.sh --apply defectdojo` successfully. TrueNAS reconciled the custom app, shared PostgreSQL and stable containers. The frontend is now attached to both `intranet` and `traefik_network` with the intended Traefik labels. HTTPS with verified TLS and SNI returns HTTP 302 to `/login?next=/`; Pi-hole `172.17.0.24` resolves the private hostname to `172.17.0.24`, and `pihole-dns-sync` logs `Added DNS: defectdojo.int.albandrieu.com -> 172.17.0.24`. Public `1.1.1.1` returns no A record. **Only pfSense/Unbound `172.17.0.1` still fails to resolve the private A record**. No authenticated API import has been tested.

The previously referenced `scripts/truenas/verify-pihole-dns-sync.sh` is not available in the operator's checkout; use the existing `diagnose-defectdojo.sh` and DNS queries below. The diagnostic's expected nonzero exit is currently attributable to Unbound only. Do not restart pfSense or alter public DNS to repair this.

```bash
# Distinguish a missing forwarder/delegation from stale cache without changing DNS.
for name in defectdojo.int.albandrieu.com hello.int.albandrieu.com; do
  for resolver in 172.17.0.24 172.17.0.1; do
    echo "=== $resolver $name ==="
    dig +time=2 +tries=1 +noall +comments +answer +authority @"$resolver" "$name" A
  done
done
# Inspect existing Unbound domain override / forwarding for int.albandrieu.com
# in pfSense UI or its read-only configuration audit; preserve canonical ownership.
```

A successful pfSense query must return `172.17.0.24` for DefectDojo without exposing the name publicly. Investigate Unbound forwarding/delegation and DNSSEC validation behavior before considering cache flushes or configuration changes.

## DNS split-view investigation — operator evidence

The operator observed `defectdojo.int.albandrieu.com` at Pi-hole `172.17.0.24` as A `172.17.0.24` with TTL 0 and `EDE: 3 (Stale Answer)` (no AA), while Unbound `172.17.0.1` returned NOERROR/NODATA with Cloudflare SOA. For `hello.int.albandrieu.com`, Pi-hole returned authoritative (`aa`) A `172.17.0.24`, whereas Unbound returned public A `82.66.4.247`. This is a **split-view DNS configuration issue**, not a DefectDojo routing issue; Traefik HTTPS already returned 302 with verified TLS. Do not assert Pi-hole DefectDojo authoritative health solely from its stale answer.

Read-only follow-up on TrueNAS:

```bash
# Compare uncached-looking query types and full flags; do not flush caches yet.
for dns in 172.17.0.24 172.17.0.1; do
  for name in defectdojo.int.albandrieu.com hello.int.albandrieu.com; do
    echo "=== $dns $name ==="
    dig +time=2 +tries=1 +noall +comments +answer +authority @"$dns" "$name" A
  done
done
sudo docker logs --since 30m pihole-dns-sync 2>&1 | grep -Ei 'defectdojo|sync|error|warn' | tail -40
```

Review pfSense DNS Resolver domain overrides / forwarding for `int.albandrieu.com`, DNSSEC behavior and Pi-hole local DNS record materialization in read-only mode. Avoid a single-name Host Override, public DNS changes, or disabling DNSSEC as a workaround. Only after confirming canonical private-zone ownership should forwarding to Pi-hole be proposed; take care to avoid a Pi-hole → Unbound → Pi-hole forwarding loop.

## Unbound incident correlation and missing private forward — 2026-10-17

The operator's `unbound-control -c /var/unbound/unbound.conf lookup defectdojo.int.albandrieu.com` selected Cloudflare authoritative nameservers (`poppy`, `vasilii`) instead of the expected Pi-hole forwarder. This is strong evidence that the active Unbound view is **not** applying the documented `int.albandrieu.com -> 172.17.0.24` Domain Override; verify effective generated config, view selection, and whether the override survived yesterday's Unbound outage before editing. The public DNS records `hello.int.albandrieu.com`, `int.albandrieu.com`, `home.albandrieu.com` point to WAN `82.66.4.247` (operator Cloudflare inventory); Hello is a documented temporary public canary, not a model for DefectDojo.

Historical precedent: `docs/incidents/2026-10-08-pfsense-unbound-oom-wan-exposure.md` records Unbound being killed by kernel memory reclaim on Netgate 1100, with CrowdSec failed-send busy-spin and pfBlockerNG ASN retries as contributors. **Do not assume yesterday's failure had the same cause without logs.** Capture current-boot and previous-day kernel/service evidence before restarting or flushing DNS.

On pfSense interactive tcsh (read-only, one command per line):

```text
unbound-control -c /var/unbound/unbound.conf status
unbound-control -c /var/unbound/unbound.conf lookup defectdojo.int.albandrieu.com
grep -nE 'int[.]albandrieu[.]com|172[.]17[.]0[.]24|forward-zone|forward-addr|domain-insecure|private-domain' /var/unbound/unbound.conf
dmesg | egrep -i 'unbound|killed|failed to reclaim|out of swap' | tail -60
ps axo pid,rss,vsz,pcpu,pmem,command | sort -nr -k2 | head -20
unbound-control -c /var/unbound/unbound.conf stats_noreset | egrep '^mem[.]'
```

From workstation run the existing read-only `scripts/pfsense/diagnose-recover.sh --check` and `scripts/pfsense/audit-posture.sh --ssh home.albandrieu.com` with existing SSH configuration. Redact secrets and avoid pasting `/conf/config.xml` wholesale. Do not add HAProxy WAN routing for private DefectDojo; DNS must be fixed first. No appliance mutation or recovery action is approved by this runbook.

## Confirmed pfSense OOM and absent generated override — operator evidence, October 17

The operator reports Unbound 1.26.1 currently running (PID 87675, uptime 45004 seconds), Python/validator/iterator modules. The generated `/var/unbound/unbound.conf` produced **no matches** for the expected `int.albandrieu.com`, Pi-hole address, forward-zone/forward-addr or split-domain directives. Combined with `unbound-control lookup` selecting Cloudflare nameservers, the active private-zone forwarding contract is absent. Verify whether the persisted pfSense Domain Override exists and why the generated config differs before modifying it. Do not add a DefectDojo-specific HAProxy route or Cloudflare record.

The current kernel ring buffer explicitly contains `pid 84666 (unbound) ... was killed: failed to reclaim memory`, alongside two PHP processes and netstat killed for the same reason. This **confirms a global memory-reclaim failure** during the observed incident, though the precise timestamp and trigger require logs. Current Unbound RSS was 131704 KiB (~129 MiB); Snort ~59 MiB, php_pfb ~50 MiB, and multiple PHP-FPM workers ~45–50 MiB each. Do not conflate process RSS totals with unique physical memory. Capture memory headroom, OOM log timestamps and pfBlockerNG/CrowdSec states before recovery. See `docs/incidents/2026-10-08-pfsense-unbound-oom-wan-exposure.md` for a prior confirmed OOM and mitigations; do not assume the same trigger.

The operator executed `scripts/pfsense/diagnose-recover.sh --check` from the TrueNAS checkout. HTTPS/API probes passed, but SSH on default port 22 timed out (exit 255), so deep evidence was **not collected**. `audit-posture.sh --ssh home.albandrieu.com` likewise timed out on port 22. Do not report the partial API diagnosis as a complete pfSense audit. The suggested workstation path `~/w/nabla-compose` did not exist on TrueNAS; on TrueNAS use `/mnt/cpool/compose/nabla-compose` and on the workstation use its actual checkout path.

New bounded read-only script (run from a host with working pfSense SSH alias/port):

```bash
bash scripts/pfsense/diagnose-unbound-split-dns.sh --check --target home.albandrieu.com
# If the SSH service uses a nonstandard port:
bash scripts/pfsense/diagnose-unbound-split-dns.sh --check --target home.albandrieu.com --port YOUR_SSH_PORT
```

This script collects Unbound status, effective forward directives, lookup selection, kernel OOM evidence, top memory processes and Unbound counters without dumping credentials or modifying pfSense. If SSH remains blocked, use the already available pfSense console to run the documented individual read-only commands. Do not attempt brute-force port discovery or enable WAN SSH for this audit.

## Correction of execution host and SSH preflight — 2026-10-17

Correction to the preceding incident narrative: the operator executed `scripts/pfsense/diagnose-recover.sh --check` and `audit-posture.sh --ssh home.albandrieu.com` **from the workstation**, not TrueNAS. The `cd ~/w/nabla-compose` command had failed in the particular shell, but the subsequent commands ran from an existing checkout; do not infer execution host from the failed `cd` alone. The workstation's `ssh -G home.albandrieu.com` reports user `albandrieu`, hostname `home.albandrieu.com`, port `22`. A TCP timeout on port 22 is a connectivity/filtering/listener problem, **not** proof of missing SSH credentials. The operator's `--port PORT_SSH` invocation was rejected by the script's numeric-port validation; `PORT_SSH` was documentation placeholder text, not a real port.

Workstation read-only checks (run from the actual checkout):

```bash
ssh -G home.albandrieu.com | grep -E '^(hostname|user|port|identityfile) '
ssh -o BatchMode=yes -o ConnectTimeout=5 -o ConnectionAttempts=1 -vv home.albandrieu.com true
bash scripts/pfsense/diagnose-unbound-split-dns.sh --check --target home.albandrieu.com
```

Use the **actual** SSH port if known; never paste `PORT_SSH` literally. For local workstation-to-pfSense testing, prefer the LAN IP `172.17.0.1` if reachable and explicitly authorized, as the public hostname can follow different WAN/firewall policy. On TrueNAS, inspect the SSH configuration and key availability **separately**, without copying workstation private keys or enabling new WAN access. A TCP timeout occurs before public-key authentication and cannot establish whether a key exists. Do not paste private keys, complete verbose logs containing sensitive identifiers, or modify pfSense SSH exposure as a workaround.

## Workstation SSH access and Unbound audit accepted — 2026-10-17

The workstation's effective `ssh -G home.albandrieu.com` resolves to `user admin`, `port 9922`, `identityfile ~/.ssh/id_ed25519`. `ssh-add -l` lists agent identities; **no private key should be copied to TrueNAS**. SSH to `172.17.0.1:22` times out, which is consistent with the wrong port, not proof of missing keys. The earlier `user albandrieu, port 22` output was from a different SSH configuration/context; the later workstation result is the successful configuration. The read-only SSH diagnostic completed against the hostname with no explicit port, proving remote access through the workstation alias.

The diagnostic returned Unbound 1.26.1, running PID 87675, uptime 45597 seconds; no generated `int.albandrieu.com` forwarding directive; public Cloudflare authoritative lookup; and kernel OOM kills for Unbound PID 84666, two PHP processes and netstat. Current Unbound RSS 131148 KiB (~128 MiB), Snort 60644 KiB, php_pfb 51172 KiB, with multiple PHP-FPM workers around 48–55 MiB RSS each. The reported Unbound cache/module counters are far below total RSS; RSS includes other allocations and shared memory, so these numbers alone do not identify the culprit. Collect dated kernel/system logs and pfSense config persistence before any change.

The SSH diagnostic can be run on the workstation using its alias:

```bash
cd ~/w/nabla-compose
bash scripts/pfsense/diagnose-unbound-split-dns.sh --check --target home.albandrieu.com
bash scripts/pfsense/audit-posture.sh --ssh home.albandrieu.com
```

Do not use `172.17.0.1:22` as the SSH target. On TrueNAS, validate a separate authorized SSH identity and port before any remote automation; do not infer that workstation SSH credentials exist there. Before restoring a Domain Override, verify Pi-hole's upstream DNS path is not Unbound for `int.albandrieu.com`, to avoid a forwarding loop. Prefer a reviewed, persistent pfSense UI/API change with read-only pre/post checks; do not edit generated `/var/unbound/unbound.conf` manually.

## Domain Override applied: forwarding timeout, Hello public fallback — 2026-10-17 23:25 CEST

After adding the `int.albandrieu.com` Domain Override, Unbound restarted (PID 55374, uptime 110 seconds). `unbound-control lookup defectdojo.int.albandrieu.com` now reports `forwarding request` to `172.17.0.24`, but with `rto 24064 msec`; direct `dig @172.17.0.1` returns SERVFAIL for DefectDojo and Hello, while the existing Vaultwarden Host Override returns authoritative A `172.17.0.24`. Pi-hole directly returns private A records for DefectDojo and Hello; verified Traefik HTTPS for DefectDojo returns 302. Therefore the remaining fault is **Unbound-to-Pi-hole forwarding reachability/behavior**, not missing domain configuration or Traefik routing.

Hello still resolves via public Cloudflare DNS `82.66.4.247` and may work through that WAN ingress or client DNS cache/fallback despite Unbound SERVFAIL; its success is **not** proof that split DNS works. DefectDojo has no public A record and must stay private. Authenticated Cloudflare inventory reports one unexpected public `.int` DNS record: inspect the detailed audit report and its exact hostname before any deletion; the public Hello exception is intentional and may not be the unexpected record.

Read-only, run from workstation and TrueNAS to isolate source-specific DNS behavior:

```bash
# On workstation: check effective LAN and public answers separately.
dig +time=2 +tries=1 @172.17.0.1 hello.int.albandrieu.com A
dig +time=2 +tries=1 @172.17.0.24 hello.int.albandrieu.com A
dig +time=2 +tries=1 @1.1.1.1 hello.int.albandrieu.com A
# On pfSense via the configured SSH alias: check LAN routing and interface policy.
ssh home.albandrieu.com 'netstat -rn -f inet | grep 172.17; grep -nE "outgoing-interface|interface:|forward-addr|private-domain|domain-insecure" /var/unbound/unbound.conf'
# On TrueNAS: inspect Pi-hole DNS listener and direct query.
sudo ss -lunpt | grep ':53 '
dig +time=2 +tries=1 @172.17.0.24 defectdojo.int.albandrieu.com A
```

Check pfSense DNS Resolver **Outgoing Network Interfaces**; previous incidents showed a WAN-only setting causing exactly this forwarding failure, whereas `All` allowed reaching the LAN Pi-hole. Do not change settings, flush cache, restart Unbound, or publish DefectDojo until source-specific reachability and the Pi-hole upstream path have been verified. Check for a Pi-hole→Unbound→Pi-hole forwarding loop. The existing `scripts/security/diagnose-private-int-dns.sh --check` correctly reports the DNS failure, but its simple A-value check does not prove Pi-hole's answer is authoritative rather than stale (EDE 3).
