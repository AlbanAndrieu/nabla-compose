# DNS and ingress ownership

This document separates DNS publication from request routing. A DNS component
decides **where a hostname resolves**. HAProxy and Traefik decide **what happens
after a client has connected**; they do not publish DNS records.

## Internal `*.int.albandrieu.com`

The repository-managed internal DNS path is:

```text
Traefik Docker labels
        |
        v
pihole-dns-sync
  DOMAIN_SUFFIX=int.albandrieu.com
  TARGET_IP=172.17.0.24
        |
        v
Pi-hole LAN DNS
        |
        v
hello.int.albandrieu.com -> 172.17.0.24
        |
        v
Traefik :443 -> service container
```

For example, `hello.int.albandrieu.com` is declared by the nginx Traefik
router. `pihole-dns-sync` is the component intended to make that hostname
resolvable on the LAN. AutoXpose is not the authoritative publisher for this
`*.int` namespace in the current repository.

The legacy Traefik Cloudflare companion explicitly excludes the `int`
subdomain tree so it must not publish `*.int.albandrieu.com` into public
Cloudflare DNS.

## Public `*.albandrieu.com`

There is not one universal publication mechanism for every public hostname.
The homelab currently has several exposure classes:

1. **Cloudflare Tunnel + Access** for services whose exposure contract says they
   are tunneled.
2. **Direct pfSense HAProxy -> Traefik** for deliberately direct hostnames.
3. **Cloudflare Tunnel + Access** for protected public services such as
   `sample.albandrieu.com`, which maps to the private origin
   `http://172.17.0.24:8091`.
4. **AutoXpose -> Cloudflare DNS / NPM** for other Docker services explicitly
   assigned to AutoXpose ownership.
5. Legacy DDNS / Traefik Cloudflare companion services that remain in the
   Traefik stack and should be consolidated over time.

`cloudflared` is therefore not equivalent to "the DNS manager for all
`*.albandrieu.com`". A Cloudflare Tunnel can create/use DNS records for its
own tunnel hostnames, but direct HAProxy/Traefik hostnames still require a
normal DNS record pointing at the public edge.

## pfSense HAProxy

HAProxy does **not** create either public or internal DNS records. Its role is
request routing after DNS resolution:

```text
client -> resolved IP -> pfSense HAProxy :443 -> Traefik :443 -> service
```

For a direct public hostname intentionally using pfSense, the DNS record must
resolve to the pfSense WAN address and HAProxy must have a host ACL/backend path
that forwards the hostname to Traefik while preserving the HTTP Host.

`sample.albandrieu.com` is no longer in that category: its target architecture
is Cloudflare Access -> Cloudflare Tunnel -> `http://172.17.0.24:8091`.

For a LAN-only `*.int.albandrieu.com` hostname resolving directly to
`172.17.0.24`, a LAN client can reach Traefik without traversing the WAN
HAProxy path. If a `*.int` name is intentionally made public, that is a
separate exposure decision and must be declared explicitly rather than inferred
from the suffix.
