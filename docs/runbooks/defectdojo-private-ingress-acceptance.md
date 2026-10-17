# DefectDojo private ingress — acceptance after PR #257

This runbook follows merged PR #257. DefectDojo's Nginx frontend is configured for the internal hostname `defectdojo.int.albandrieu.com` on Traefik `websecure`; public Cloudflare DNS, AutoXpose and WAN HAProxy are **not** part of the intended path.

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
