# hello.int.albandrieu.com — Traefik cutover

State: **repository-ready, runtime NOT accepted**, 2026-10-10.
The service already had Traefik Docker labels before this PR; the PR
pins the Docker network and port. **No TrueNAS app was redeployed, no
pfSense/Cloudflare DNS rule was changed, and NPM/NPMplus remain untouched.**

## Intended traffic ownership

```text
private Pi-hole DNS -> 172.17.0.24:443 -> Traefik hello@docker -> nginx:80
public exception DNS -> pfSense HAProxy -> 172.17.0.24:443
  -> Traefik hello@docker -> nginx:80
```

Avoid double registration of the same Host rule in the Traefik file
provider or another Compose project. The hello app must join the external
`traefik_network` and Traefik must be able to resolve it by Docker
provider. The source no longer depends on NPM/NPMplus. The existing direct
Nginx port 8099 remains for isolated backend health and rollback.

## Read-only preflight (on TrueNAS)

Run against the **deployed** checkout, not just GitHub; do not paste
credentials or full access logs into an agent transcript.

```bash
midclt call app.query '[["id","in",["nginx","traefik","nginx-proxy-manager","npmplus"]]]' |
  jq '[.[] | {id,state}]'
docker ps --format '{{.Names}} {{.Status}} {{.Image}}' |
  grep -E '(^nginx |^traefik |nginx-proxy-manager|npmplus)' || true
docker inspect nginx traefik |
  jq '[.[] | {name:.Name,networks:(.NetworkSettings.Networks|keys),
       ports:.NetworkSettings.Ports}]'
docker network inspect traefik_network |
  jq '.[0] | {name:.Name,containers:(.Containers|keys)}'
curl -fsS --max-time 5 -o /dev/null -w 'hello backend http=%{http_code}\n'   http://172.17.0.24:8099/
curl -skS --resolve hello.int.albandrieu.com:443:172.17.0.24   --max-time 8 -o /dev/null   -w 'Traefik origin http=%{http_code}\n'   https://hello.int.albandrieu.com/
dig +short @172.17.0.1 hello.int.albandrieu.com
dig +short @172.17.0.24 hello.int.albandrieu.com
```

Also check the active Traefik router list and any NPM proxy-host for this
hostname. Existing public DNS exception `config/public-int-dns-exceptions.txt`
must not be expanded just to force a passing result.

## Explicit cutover and acceptance

1. Confirm no other proxy or Docker project currently owns this hostname.
   Capture existing NPM/NPMplus route state and save rollback configuration.
2. Verify the deployed Nginx Compose includes network `traefik_network`,
   `traefik.docker.network=traefik_network` and
   `traefik.http.services.hello.loadbalancer.server.port=80`.
   If not, use the supported TrueNAS app lifecycle to apply **only** the
   hello app from the approved checkout. Do not restart pfSense or Traefik.
3. Test direct Traefik origin with `curl --resolve` above; check it
   returns the same intended hello content as port 8099 (not another
   virtual host, 404 or 502). Verify SNI/TLS separately **without** `-k`
   from a trusted client. A 2xx/3xx code alone is not sufficient.
4. Check the LAN split DNS and the pfSense HAProxy/public exception
   separately. Verify forwarding headers with trusted-source controls.
   HTTP redirects, ACME, error pages and firewall exposure must remain
   unchanged outside this hello route.
5. Leave old NPM/NPMplus apps stopped only after a separate consumer
   inventory and manual acceptance. **Never run Compose down with
   `--volumes`** or delete stored TLS material during this cutover.

**Done:** hello origin and intended user path pass, route registered once,
no external regression, documented rollback and explicit runtime evidence.
**Rollback:** restore the saved NPM proxy-host rule or previous hello app
revision via TrueNAS; do not repoint unrelated `*.int` DNS entries.
**Defer:** CrowdSec enforcement and any proxy-app/data deletion until
real-client-IP handling and false-positive canary tests pass.
