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
sudo bash scripts/truenas/verify-pihole-dns-sync.sh
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
