# TrueNAS GUI/API: pfSense HAProxy → Cloudflare Tunnel + Access

**State: CODED, NOT_APPLIED / NOT_TESTED from the public Internet.** This file does not authorize a production apply. The old public `:7000` listener is gone with pfSense (18 November 2026); the internal TrueNAS HTTPS/API listener on `172.17.0.24:7000` is retained for CSI and LAN clients. **Do not globally replace internal WebSocket `wss://...:7000/api/current` endpoints.**

## Desired boundary

- Browser: `https://truenas.albandrieu.com/ui/signin` on public **443**, not `:7000`.
- Cloudflare Tunnel origin: `https://172.17.0.24:7000` with TLS certificate hostname `truenas.albandrieu.com` verified (no `no_tls_verify`).
- Cloudflare Access: `truenas-admin` behind the existing `nabla` identity policy, **no Everyone bypass and no generic service-token bypass**. TrueNAS login is still required.
- The cloudflared process must be able to reach 172.17.0.24:7000 from its network. No new Freebox port forward, DMZ or inbound NAT rule.
- `truenas.albandrieu.com/A` is present in the historical DNS ID inventory from pfSense. **An A and a CNAME cannot coexist.** Check the *live* DNS record, not only code, before an apply.

## Safe cutover steps (operator approved)

1. From TrueNAS/cloudflared network, confirm the origin TLS and SNI without disabling certificate validation:
   `curl --resolve truenas.albandrieu.com:7000:172.17.0.24 --fail --head https://truenas.albandrieu.com:7000/`
   If the certificate is not trusted, fix its issuing CA or configure Cloudflare Tunnel `ca_pool`; do not blindly set `no_tls_verify=true`.
2. Inspect current DNS with `scripts/cloudflare/capture-dns-records.py` (read-only). The old `A` is tagged as retired in historical records but may still be live. **Retire/import the legacy A in an isolated reviewed DNS plan first**; never apply a plan that destroys unrelated names.
3. Review `scripts/infra/terragrunt-safe.sh infrastructure/cloudflare plan`: **only** TrueNAS Access app, tunnel route and proxied CNAME are expected from this change, plus any separately approved existing drift. If an old A exists, a record conflict is expected: stop and retire it first. Check provider state/plan, not only syntax.
4. Apply only the reviewed plan on an authorized workstation with the dedicated Cloudflare token/state. No apply in CI.
5. External acceptance: anonymous `https://truenas.albandrieu.com/ui/signin` returns Access challenge/deny (typically 302 or 403), **never the TrueNAS login page directly**. With Access identity, TrueNAS login should load and WebSocket connections should succeed. Confirm `dig` reports a proxied tunnel CNAME (Cloudflare can flatten the public answer).
6. Confirm `https://truenas.albandrieu.com:7000/ui/signin` is not a supported public path, no Freebox forward exists, and `scripts/infra/terragrunt-safe.sh infrastructure/cloudflare plan` is empty. Preserve direct LAN API for CSI.

Rollback: restore the old DNS only if an approved, secured origin exists; **never** re-publish the bare TrueNAS management listener on the WAN. Roll back tunnel ingress and Access together after separate validation.
