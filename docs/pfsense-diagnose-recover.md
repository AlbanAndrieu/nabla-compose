# pfSense diagnosis and bounded recovery

`nabla-compose` owns pfSense operational diagnostics and recovery. `fastapi-sample`
consumes read-only pfSense evidence but must not own appliance administration or
recovery logic.


## Incident WAN Freebox bridge — 15 novembre 2026

**Statut : diagnostic ouvert, retour d'Internet non prouvé.** L'opérateur
confirme la Freebox fibre en bridge, l'adresse publique Free
`82.66.4.247` et le préfixe IPv6 `2a01:e0a:a17:3c00::/64`.
L'adresse privée `10.52.47.193` affichée ailleurs dans Freebox OS
n'est pas l'adresse WAN publique. L'ADSL indiqué DOWN ne suffit pas
à diagnostiquer une panne de la fibre.

| Élément | Observation utilisateur |
| --- | --- |
| WAN | `mvneta0.4090` / VLAN 4090, `82.66.4.247/24` |
| Route IPv4 | `default -> 82.66.4.254` présente |
| ARP gateway | `82.66.4.254 -> 8c:97:ea:39:b3:7b` (correspondance en cache possible) |
| Ping depuis WAN | 3/3 pertes vers `82.66.4.254` et `1.1.1.1` |
| TCP IPv4 | `nc -4 -vz -w 5 1.1.1.1 443` : `Permission denied` |
| Route IPv6 | `default -> fe80::8e97:eaff:fe39:b37b%mvneta0.4090` |
| Source IPv6 WAN | `fe80::f2ad:4eff:fe23:2f99` (link-local uniquement) |
| IPv6 Internet | Ping `2606:4700:4700::1111` : 100 % de pertes |

### Modification opérateur — WAN « Disable Gateway Monitoring »

L'opérateur a **activé `Disable Gateway Monitoring`** pour la
passerelle WAN IPv4. Cette action désactive `dpinger` et la télémétrie
de disponibilité ; **elle ne restaure pas le transport IP**.
La documentation Netgate distingue
[`Disable Gateway Monitoring Action`](https://docs.netgate.com/pfsense/en/latest/routing/gateway-configure.html),
qui maintient les mesures tout en supprimant les actions automatiques
lors des changements de statut. Après résolution, évaluer cette seconde
option sur le WAN unique avec une cible Monitor IP réellement joignable.
Ne pas considérer la passerelle comme vérifiée UP si elle n'est plus surveillée.

### Plan de reprise IPv4 (lecture seule avant toute mutation)

1. Confirmer `ifconfig mvneta0.4090`, `netstat -rn -f inet`,
   `route -n get 1.1.1.1`, `arp -an`. Ne pas changer
   l'IPv4 publique, le masque, la gateway ou le VLAN sans preuve.
2. Tester avec `Diagnostics > Ping` (source WAN, IPv4)
   `1.1.1.1`, puis un test TCP vers `1.1.1.1:443`.
   La réponse `Permission denied` justifie la recherche d'un
   **blocage PF local** ; elle ne prouve pas un défaut Free.
3. Lire `Status > System Logs > Firewall` et les règles PF
   (`pfctl -sr`, sans modification). Capturer via
   `Diagnostics > Packet Capture` sur l'interface WAN
   **`mvneta0.4090`**, filtre `arp or icmp or host 1.1.1.1`,
   pendant un ping depuis pfSense : aucun paquet sortant => piste
   locale ; sortie sans réponse => piste amont / filtrage retour ;
   réponse visible => examiner le traitement pfSense.
4. Refaire les tests depuis un client du LAN `172.17.0.0/24`
   sans VPN/données mobiles. Si pfSense réussit mais pas les clients,
   vérifier les règles LAN et le SNAT dans
   `Firewall > NAT > Outbound`. Tester l'accès numérique avant
   toute modification Unbound ou Cloudflare.

**DONE IPv4** : transport TCP/HTTPS IPv4 confirmé depuis pfSense
et client LAN, route et SNAT cohérents, tests datés et tracés.
Le DNS direct et le reverse PTR Free sont des sujets distincts.

### Plan IPv6 — objectif de la roadmap

- Vérifier dans Freebox OS les routes /64 IPv6 et le **next hop**
  vers pfSense. Le WAN peut légitimement n'avoir qu'une link-local
  `fe80::` si Free route un préfixe LAN vers lui.
- Vérifier si `2a01:e0a:a17:3c00::/64` est **réellement routé**
  vers le LAN pfSense ; ne pas attribuer le même /64 à plusieurs
  interfaces. Contrôles read-only :
  `netstat -rn -f inet6`, `ifconfig mvneta0.4091`,
  `ndp -an`, puis
  `ping6 -c 3 'fe80::8e97:eaff:fe39:b37b%mvneta0.4090'`.
- Après adressage LAN, vérifier RA/SLAAC (mode Assisted relevé,
  compatible Android), règles IPv6 LAN/WAN sans ouverture entrante
  supplémentaire, connectivité IPv6 littérale
  `2606:4700:4700::1111` depuis un client LAN, puis DNS AAAA.
  Préserver `Unbound > Outgoing Network Interfaces = All`
  pour le Domain Override privé [déjà documenté](dns-ingress-ownership.md).

**DONE IPv6** : /64 global LAN, client SLAAC opérationnel,
route IPv6 Internet, tests AAAA et sécurité ingress vérifiés
depuis le LAN après redémarrage.


### Mise à jour opérateur — connectivité TCP IPv4 confirmée (15/11/2026)

Après les premières investigations PF/IPS, deux tests exécutés dans le
contexte de diagnostic pfSense ont désormais réussi :
- `nc -4 -vz -w 5 1.1.1.1 443` — **TCP CONNECT OK** ;
- `nc -4 -vz -w 5 9.9.9.9 443` — **TCP CONNECT OK**.

**Statut : `PF_IPv4_TCP_EGRESS_PASS`, mais `LAN_E2E_NOT_VERIFIED`.**
Cette observation démontre l'accès TCP sortant depuis pfSense à deux
destinations Internet. Elle **ne prouve pas** que la route LAN/NAT,
la résolution DNS/Unbound, ICMP ou IPv6 fonctionnent. Le changement
précis ayant permis ce rétablissement n'a pas été communiqué :
ne pas attribuer causalement la réparation à CrowdSec, Snort,
pfBlockerNG ou à `Disable Gateway Monitoring` sans preuve.

Recette suivante : effectuer `curl -4 -I --connect-timeout 5
https://www.cloudflare.com` depuis un client LAN, tester
`Diagnostics > DNS Lookup` sur pfSense et
`dig @172.17.0.1 www.cloudflare.com A` depuis le LAN ;
réactiver *une par une* les protections temporairement arrêtées, en
répétant `nc` et en relevant tout retour de `Permission denied`.
Restaurer le niveau de protection initial après attribution de la
cause ; ne jamais désactiver globalement PF. Poursuivre séparément
le rétablissement IPv6 du LAN.


### Évolution de l'incident — connectivité workstation toujours absente (15/11/2026)

L'opérateur précise avoir **arrêté les trois protections simultanément**
(CrowdSec, Snort, pfBlockerNG). Les connexions TCP depuis pfSense vers
`1.1.1.1:443` et `9.9.9.9:443` ont réussi **après** ces arrêts,
sans que cette chronologie permette d'attribuer la cause à l'une
des trois. Entre-temps, le WebConfigurator pfSense est décrit comme
**extrêmement lent / difficile d'accès**, tandis que la workstation
signale **aucune connexion Internet** et que `ping cloudflare.com`
échoue (résolution DNS ou ICMP non distingués).

**État corrigé du diagnostic : `WAN_IPV4_TCP_OK`,
`LAN_IPV4_UNKNOWN`, `LAN_DNS_UNKNOWN`, `PFSENSE_PERF_DEGRADED`,
`ROOT_CAUSE_UNKNOWN`.** Ne pas conclure que la connectivité LAN
est revenue ; ne pas réactiver trois systèmes IPS simultanément.

Préflight prioritaire depuis la workstation `172.17.0.57` :
`ip -4 route get 1.1.1.1`, `ping -c 3 172.17.0.1`,
`nc -4 -vz -w 5 1.1.1.1 443`,
`dig +time=2 +tries=1 @172.17.0.1 cloudflare.com A`.
Si TCP externe échoue alors que pfSense le réussit,
vérifier règles LAN et `Firewall > NAT > Outbound`. Si TCP
externe réussit mais le DNS local échoue, contrôler Unbound,
sa réponse sur `172.17.0.1:53`, DNSBL et la configuration de
résolveur de la workstation. Si la lenteur persiste,
utiliser SSH **direct LAN** plutôt que le FQDN public/HAProxy,
puis `uptime`, `swapinfo -h`, `top -aSH` et `netstat -m`
(sans restart global), conformément au
[guide Netgate](https://docs.netgate.com/pfsense/en/latest/troubleshooting/high-cpu-load.html).

**Recette encore ouverte :** accès IPv4 et DNS depuis la workstation,
stabilité WebConfigurator, puis réactivation **une par une**
des protections, avec tests après chaque étape.


### Relevé workstation/Unbound du 15/11/2026 — P0 DNS

Après arrêt de **CrowdSec, Snort et pfBlockerNG**, le TCP IPv4 depuis
pfSense réussit vers `1.1.1.1:443` et `9.9.9.9:443`.
La workstation indique `ip -4 route get 1.1.1.1` via
`172.17.0.1` ; le ping de la passerelle LAN a reçu 3/3 réponses
et SSH direct vers pfSense fonctionne. Le `dig` LAN dirigé vers
`172.17.0.1` **expire sans réponse**. La charge observée est
inférieure à 1 ; `swapinfo -h` n'a retourné aucune donnée exploitable.
**Conclusion :** réseau workstation ↔ pfSense opérationnel ;
service DNS local **non fonctionnel depuis le LAN** ; le test TCP
direct workstation ↔ Internet et la cause du timeout DNS sont
encore **NOT_VERIFIED**. Ne pas déduire de l'absence de swap une
pression mémoire ni du faible load l'absence de problème DNS.

Prochain diagnostic sans mutation, d'abord workstation :
`nc -4 -vz -w 5 1.1.1.1 443`,
`dig +time=2 +tries=1 @9.9.9.9 cloudflare.com A`,
`dig +time=2 +tries=1 @172.17.0.1 cloudflare.com A`
et `dig +tcp +time=2 +tries=1 @172.17.0.1 cloudflare.com A`.

Sur pfSense, en SSH direct LAN :
`pgrep -laf unbound`,
`sockstat -4 -l | grep ':53'`,
`unbound-control -c /var/unbound/unbound.conf status`.
Dans l'UI : `Status > Services > DNS Resolver`,
`Status > System Logs > System/DNS Resolver`,
puis `Services > DNS Resolver` : écoute `LAN` ou `All`
sur UDP/TCP 53, ACL LAN autorisée, et
`Outgoing Network Interfaces = All` (contrat private override).
Si Unbound n'est pas actif, démarrer/redémarrer **uniquement Unbound**
via `Status > Services`, puis retester le DNS LAN.
Le projet utilise Unbound en résolution récursive, avec
`int.albandrieu.com` délégué à Pi-hole `172.17.0.24`.
Ne pas basculer aveuglément le DNS privé vers Quad9 et
ne pas réactiver les trois protections en même temps.

## Auto Config Backup (ACB) et notices `write_config`

Statut : **`ACB_UPLOAD_NOT_VERIFIED`** depuis l'échec d'upload chiffré du
27/10 22:46:33 (`curl (28)`, timeout) ; provenance du
`write_config() was called without description` de 22:45:52 inconnue. Deux
événements distincts : leur proximité ne prouve pas une cause commune.
Aucune modification DNS, WAN, pare-feu, certificat, Device Key, mot de passe
de chiffrement ou ACL n'est nécessaire pour diagnostiquer.

Lecture des preuves :

- ACB utilise des **POST authentifiés** sur `/list`, `/save` et `/getbkp`
  ([`acb.inc`](https://github.com/pfsense/pfsense/blob/master/src/etc/inc/acb.inc)) :
  un `HEAD /` ou `GET /` anonyme vers `acb.netgate.com` n'exerce aucun de ces
  parcours et ne prouve rien (ni succès, ni panne). Ne jamais fabriquer de
  `POST /list` ou `/save` à la main.
- **Hosted backup count: 100** est le plafond de rétention Netgate (les plus
  anciennes sont évincées) : ni quota bloquant, ni preuve d'upload récent.
- `acb_backup_upload()` supprime les fichiers staged `.form`/`.data` quelle
  que soit l'issue : `staged=0` ne prouve pas la réussite.
- `ssl_verify_result=0` signifie seulement qu'aucun échec de vérification du
  certificat n'a été rapporté.
- `/tmp/acb_debug.txt` (écrit sur erreur curl) peut contenir des paramètres
  sensibles : ne jamais l'afficher ni le partager, comme `config.xml`, la
  Device Key ou les paramètres ACB. Pas de `curl -v`, `--trace` ni `-k` sur
  une requête ACB authentifiée.

Réception (UI pfSense, après un backup local chiffré via
`Diagnostics > Backup & Restore`, sans jamais restaurer en production) :

1. `Services > Auto Config Backup > Restore` : noter l'horodatage de l'entrée
   hébergée la plus récente (vérifier l'ordre d'affichage) et
   `Staged backups waiting to upload`.
2. `Services > Auto Config Backup > Backup Now` : créer **une seule** entrée
   avec une *Revision Reason* descriptive, sans changer Device Key ni mot de
   passe.
3. Après au moins une minute (Netgate traite la file environ chaque minute),
   vérifier l'entrée dans `Restore` et les lignes `acbupload.php`
   *Staging → Starting upload → Completed (success)* de
   `Status > System Logs > System > General`.
4. Si absente : diagnostiquer **depuis pfSense** (`Diagnostics > DNS Lookup`,
   `Status > Gateways`, `Diagnostics > Routes`, NTP et CA système), sans
   relance en boucle ni changement WAN/TLS.

Provenance `write_config` : chercher le contexte de l'appel dans
`Status > System Logs > System > General` et
`Diagnostics > Backup & Restore > Config History`. Le seul appel du dépôt,
`scripts/pfsense/manage-api-identities.php`, passe déjà le motif
`Reconciled pfSense REST API service identities` : rien ne l'incrimine. Si un
autre appelant est démontré, corriger **son** appel en
`write_config("motif explicite")` (test et rollback), sans masquer le message
ni patcher les fichiers système pfSense.

| Contrôle | Condition DONE | Si information absente |
| --- | --- | --- |
| ACB stockage distant | nouvelle entrée dans `Restore`, datée après l'incident, déchiffrement vérifié en privé | `ACB_UPLOAD_NOT_VERIFIED` |
| ACB transport | DNS/HTTPS pfSense corrects et `Backup Now` reçu côté service | `ACB_TRANSPORT_NOT_VERIFIED` |
| Avertissement config | appelant identifié, pas de récurrence après correctif ciblé | `WRITE_CONFIG_PROVENANCE_UNKNOWN` |
| Intégrité runtime | UI, règles, passerelles et services inchangés | STOP, diagnostic séparé |

Une entrée présente et récupérable donne `ACB_UPLOAD_PASS` ; un échec
explicite dans les journaux, `ACB_UPLOAD_FAILED`. Ne jamais clore en effaçant
la notification GUI avant d'avoir vérifié l'état distant. Sources :
[ACB status](https://docs.netgate.com/pfsense/en/latest/backup/acb-status.html),
[ACB info](https://docs.netgate.com/pfsense/en/latest/backup/acb-info.html),
[`config.lib.inc`](https://github.com/pfsense/pfsense/blob/master/src/etc/inc/config.lib.inc),
[libcurl errors](https://curl.se/libcurl/c/libcurl-errors.html).

## Incident 502 WebConfigurator / REST API (September 2026)

**First failing layer:** a native nginx HTTP 502 proves that DNS/TCP/TLS and
the HTTP listener responded, while the PHP-FPM/webConfigurator upstream did not
serve the request. It does **not** prove an invalid API key, a PF block, or an
Unbound failure. See the
[dated pfSense platform incident](./incidents/2026-09-08-pfsense-webconfigurator-http-502.md)
for the historical evidence and the
[FastAPI incident register](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/incidents.md)
for the original observer chronology.

### Collect evidence before any recovery

Use `scripts/pfsense/diagnose-recover.sh --check` **from the operator
workstation**. The helper captures bounded nginx/PHP-FPM sockets and process
status, filesystem/swap/RSS/OOM evidence, Unbound, Snort/pfBlockerNG/PF tables,
the management port 10443 and independent UI/REST vantage points.
Do not repeat a rejected KeyAuth request: the helper fails fast on HTTP 401.

If additional on-appliance evidence is necessary, use a reviewed pfSense shell
session and run the following **read-only, single-line** commands individually:

```text
sockstat | egrep 'nginx|php-fpm|unbound'
pgrep -laf 'nginx|php-fpm|unbound'
df -h
df -i
swapinfo -h
tail -n 250 /var/log/system.log
```

Preserve failure-time logs and OOM details before restarting a service.
Review `/crash_reporter.php` for embedded configuration/secrets before sharing
any report. A concurrent Unbound failure must be assessed separately with
`unbound-control -c /var/unbound/unbound.conf status`.

### Recovery boundary and acceptance

Use the canonical helper's explicit `--apply` mode only after reviewing
`--check` evidence and confirming the SSH management path. The bounded
recovery may restart PHP-FPM/webConfigurator and, only if indicated, Unbound.
Do **not** reboot the firewall as the first response. Do not flush PF tables,
weaken firewall/Snort/pfBlockerNG policy or bulk-unblock sources;
`--unblock-sources` is a separate exact-host opt-in.

Close the incident only after verifying:

1. WebGUI/PHP-FPM recovered without an unnecessary firewall reboot;
2. authenticated `GET /api/v2/system/version` returns 2xx JSON from the
   trusted LAN/TrueNAS observer, not merely an HTTP listener response;
3. Unbound is evaluated independently;
4. `pfsense_exporter` metrics are independent of REST control-plane health;
5. Gatus/Uptime Kuma/FastAPI probes are low-frequency, offset and bounded
   (no synchronous deep-status probes or immediate retry storms on HTTP 5xx);
6. the recurrence evidence preserves process/socket/log/OOM observations.

FastAPI probe caching, stale/unknown semantics and source-specific timeout
contracts remain in
[fastapi-sample's observer note](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/pfsense-webconfigurator-recovery.md).

## Direct LAN SSH by default; HTTPS outage fallback (15 November 2026)

SSH-based pfSense diagnostic scripts now default to
`admin@172.17.0.1:9922` (variables `PFSENSE_SSH_TARGET` and
`PFSENSE_SSH_PORT`). This avoids dependence on public DNS or
HAProxy. Explicit CLI flags and environment overrides are still supported.
High-impact scripts requiring an explicit target for authorization remain
unchanged.

When public and LAN HTTPS probes both fail, `--check` **does not quit
before SSH diagnostics**: it records both probe failures and attempts SSH
directly. A successful SSH run is reported as **partial diagnostics**,
not as a working web GUI. `--api-only` remains strict, and failure of
both HTTPS and SSH is still an error.

```bash
bash scripts/pfsense/diagnose-recover.sh --check --no-auto-egress
bash scripts/pfsense/diagnose-unbound-restart-cause.sh --check
bash scripts/pfsense/diagnose-unbound-split-dns.sh --check
```

The bounded `diagnose-recover.sh --apply` recovery over SSH still
restarts PHP-FPM/webConfigurator and only restarts Unbound if the
internal health check fails. In contrast,
`reconcile-php-fpm.sh --apply` **also changes the PHP-FPM profile**
and retains its mandatory explicit confirmation.

## Emergency pfSense access — quick SSH-only recovery (15 November 2026)

The workstation can reach pfSense SSH at `admin@172.17.0.1:9922` even
when DNS and HTTPS are down. Use the lightweight, standalone
`scripts/pfsense/recover-access.sh` rather than the full
`diagnose-recover.sh` API/HTTPS probe matrix.

| Manual command from `nabla-compose` | Result |
| --- | --- |
| `just pfsense-check` | Short **read-only** DNS, Unbound, PHP-FPM, GUI checks |
| `just pfsense-dns` | Restart **only Unbound** |
| `just pfsense-ui` | Restart **only PHP-FPM + WebConfigurator** |
| `just pfsense-recover` | Restart Unbound, then PHP-FPM + WebConfigurator |

Alternative without `just`: `bash scripts/pfsense/recover-access.sh
--check`, `--dns`, `--ui`, or `--all`. The default target/port may be
overridden via `PFSENSE_SSH_TARGET`, `PFSENSE_SSH_PORT` or explicit
`--target` / `--port`. The script uses strict host-key checking, requires
root-equivalent SSH authorization for restart modes, and does **not**
modify routing, PF rules, IPS services, packages or PHP-FPM pool sizing.
Restarting the GUI may interrupt the existing WebConfigurator session.
An offline diagnostic is not a service health attestation.

### When workstation Internet/DNS is already broken

The new commands above require a checkout containing this PR. If the
workstation cannot fetch GitHub because of its current DNS outage, use
pfSense's **existing** native recovery commands immediately (no install,
download, or new script required):

```bash
# Unbound only — can be run without a working webConfigurator or external DNS.
ssh -p 9922 admin@172.17.0.1 '/usr/local/sbin/pfSsh.php playback svc restart unbound'

# Only if the GUI remains degraded — restarts PHP-FPM and webConfigurator.
ssh -p 9922 admin@172.17.0.1 '/etc/rc.php-fpm_restart && /etc/rc.restart_webgui'

# Separate DNS tests from the workstation: local UDP, local TCP, public resolver.
dig +time=2 +tries=1 @172.17.0.1 example.com A
dig +tcp +time=2 +tries=1 @172.17.0.1 example.com A
dig +time=2 +tries=1 @9.9.9.9 example.com A
```

These commands do not disable pfSense firewall rules or restart the whole
appliance. If Unbound starts successfully but LAN DNS still times out,
investigate ACL/binding/PF rather than repeatedly restarting it.

### Confirmed DNS evidence (15/11/2026, operator)

- Workstation direct DNS to **9.9.9.9** succeeds (third `dig`):
  public UDP DNS transport and IPv4 routing/NAT work at least for this path.
- Workstation queries to **172.17.0.1** still time out.
- pfSense `pgrep -x unbound` returns two lines, which does **not**
  demonstrate that the service listens or answers.
- pfSense `drill -t A example.com @127.0.0.1` reports
  `error sending query: could not send or receive`.

**Current hypothesis:** Unbound listener, binding, runtime health or local
resolver filtering; no evidence yet identifies the cause. Inspect
`sockstat -4 -l | grep ':53'`, `unbound-control -c
/var/unbound/unbound.conf status`,
`unbound-checkconf /var/unbound/unbound.conf`, and the
DNS Resolver log. Compare the specific listening addresses with the
workstation and loopback queries. If localhost and LAN both fail,
an ACL issue affecting only LAN clients is insufficient to explain all
observations.

For the intended architecture, use **Network Interfaces = LAN and
Localhost** (plus any other deliberate internal DNS clients) versus
**Outgoing Network Interfaces = All**: these options serve different
purposes. Keep `int.albandrieu.com` delegated to Pi-hole only via
pfSense Unbound. See [Netgate DNS Resolver configuration](https://docs.netgate.com/pfsense/en/latest/services/dns/resolver-config.html)
and [Unbound access lists](https://docs.netgate.com/pfsense/en/latest/services/dns/resolver-acls.html).

### DNS diagnosis and root-cause classification

The read-only check compares workstation DNS UDP and TCP to
`172.17.0.1:53`, direct DNS to `9.9.9.9:53`, and on pfSense itself
DNS via `127.0.0.1`, `172.17.0.1` and `9.9.9.9`. It also reports Unbound's
process/control status, IPv4 DNS listeners, PHP-FPM socket and bounded
Unbound/OOM errors.

| Observation | Leading diagnosis (verify before changing config) |
| --- | --- |
| Unbound process missing | Daemon crash / OOM / watchdog not running |
| No IPv4 listener on 53 | Unbound not binding expected interface |
| Loopback DNS succeeds but workstation LAN DNS times out | LAN binding, Unbound access-control or PF filter |
| DNS at pfSense loopback fails while direct 9.9.9.9 succeeds | Unbound recursion/config/DNSSEC |
| DNS direct to 9.9.9.9 also fails | Outbound DNS transport / filtering / route |
| Workstation TCP DNS succeeds but UDP fails | UDP/53-specific filtering |
| Workstation DNS works but browser does not | Workstation resolver selection/cache, or HTTPS issue |

A healthy Unbound PID or successful HTTPS from **pfSense itself** does
not prove LAN DNS or NAT functionality. The documented configuration
keeps `Forwarding Mode disabled`, `Outgoing Network Interfaces = All`
and the `int.albandrieu.com` override toward Pi-hole `172.17.0.24`.
Do not change them without first reproducing the failing layer.

Read-only results precede explicit restarts; after restoring functionality,
reactivate Snort, CrowdSec and pfBlockerNG **one at a time** and check
DNS/IPv4 after each. On this Netgate 1100, examine the
[13/11 OOM incident](incidents/2026-11-13-pfsense-unbound-oom-snort-crowdsec.md)
before allowing resource-intensive IDS/IPS updates.

### Réparation du Domain Override et inventaire de dérive (15/11/2026)

La restauration de l'accès DNS public après reboot **ne rétablit pas**
la zone interne. `just pfsense-split-dns-check` et
`just pfsense-split-dns-apply` réparent uniquement le transfert de
`int.albandrieu.com` vers Pi-hole, avec `outgoing_interface=all`.
`just pfsense-drift` agrège cet invariant, l'audit posture/capacité
et les preuves du Boot Environment ; voir
[contrat de réparation et de portée](dns-ingress-ownership.md).

## Normal read-only check## Normal read-only check

From the workstation:

```bash
scripts/pfsense/diagnose-recover.sh --check
```

The helper first validates the HTTPS/UI and REST API v2 control paths, then tries
to collect deeper appliance evidence over SSH. A failed SSH connection does not
discard successful HTTPS/API evidence in `--check` mode.

If SSH is intentionally filtered or unavailable, use:

```bash
scripts/pfsense/diagnose-recover.sh --api-only
```

Two independent least-privilege identities are evaluated when their keys are
present in the caller environment:

- `PFSENSE_POSTURE_API_KEY`: the four posture GET endpoints must return `200`
  and `/api/v2/diagnostics/table?id=snort2c` must return `403`;
- `PFSENSE_SECURITY_API_KEY`: the Snort table endpoint must return `200` and
  `/api/v2/status/services` must return `403`.

Each key is written to its own mode-0600 temporary curl header file so no secret
is placed on the curl command line, sent through SSH, or printed in the report.
A `401` is therefore an authentication result, a `403` can be an expected
least-privilege result, while `http=000` is reported with the curl exit code and
transport timings instead of being collapsed into an authentication failure.

### Authentication lockout guard

REST API KeyAuth failures can feed pfSense REST API Login Protection and its
`sshguard` table. This matters because a stale 64-character key can initially
produce normal HTTP `401 AUTH_AUTHENTICATION_FAILED` responses and, after
several attempts, the same workstation can observe HTTPS and SSH connection
timeouts even though nginx/WebConfigurator remains healthy for another source.

The helper therefore performs a single posture-key preflight against
`/api/v2/system/version`. If it returns HTTP 401, the remaining authenticated
posture and security matrices are skipped. Do not repeatedly rerun the helper
with a rejected key.

Observed incident sequence on 2026-10-04:

1. UI hostname and LAN probes returned HTTP 200;
2. three posture API calls with the stale workstation key returned HTTP 401;
3. subsequent API calls and SSH from that source timed out;
4. a separate LAN request still returned HTTP/2 200 from nginx.

The sequence initially made Login Protection/`sshguard` a reasonable
hypothesis, but appliance evidence subsequently **invalidated it as the cause of this incident**:
`pfctl -t sshguard -T show` was empty, including for
`172.17.0.57`. The fail-fast guard remains useful defensive behavior because a
diagnostic must not emit a burst of rejected credentials, but a timeout after a
401 must not be attributed to `sshguard` without a matching table entry.

Later evidence also proved that SSH itself was healthy: `sshd` listened on
`*:9922`, the LAN anti-lockout rule allowed TCP/9922, and a direct
`admin@172.17.0.1:9922` connection completed key exchange and public-key
authentication. The workstation resolves `home.albandrieu.com` to the public
WAN address `82.66.4.247`, so FQDN SSH exercises a different/hairpin path from
direct LAN administration. Existing OpenSSH ControlMaster sockets can additionally
produce a misleading `mux ... Broken pipe`; recovery diagnostics deliberately
disable multiplexing.

The recovery helper intentionally never removes `sshguard` entries
automatically.

The SSH evidence also reports, without secret material:

- REST API enabled/read-only/login-protection/auth-method settings;
- whether `fastapi_posture` and `fastapi_security` exist, are enabled and are
  outside the `admins` group;
- exact privileges, including missing or unexpected grants;
- API-key owner, byte length, hash algorithm, description, hash presence and key
  count. The key value and stored hash are never emitted.

The helper probes both the configured hostname path and the direct LAN address.
The direct IP probe intentionally disables certificate hostname validation because
it is transport comparison evidence; the hostname probe remains the TLS-trust
proof.

The helper discovers FastAPI Cloud egress from `/api/runtime/topology` and
falls back to the shared `/api/health-board` runtime projection when that route
is not exposed by the active deployment. A failed egress discovery never removes
the explicit LAN observer sources.

Authenticated matrices are fail-fast: a first `401` stops further KeyAuth
requests, including the second identity, to avoid feeding REST API Login
Protection/sshguard. Transport output uses a non-whitespace field separator so
an empty curl `remote_ip` remains `peer=unknown` instead of shifting latency
fields.


## Workstation console output

`scripts/pfsense/console.sh` formats the workstation-side pfSense diagnostics
(Unbound, Snort, pflow, memory, split DNS, Prometheus, WhatsApp, CrowdSec).
It runs **only on the workstation**: remote commands stay plain `/bin/sh`,
with nothing installed or colored on pfSense. Native helpers
(`check-central-crowdsec-bouncer.sh`, `manage-api-identities.php`) do not load
it; `audit-posture.sh` and `diagnose-recover.sh` keep their own colored
summaries.

| Context | Output |
| --- | --- |
| Workstation TTY | 🔎 sections, ✅ / ⚠️ / ❌ status, colors and summary |
| `PFSENSE_OUTPUT=compact` | condensed view even without a TTY; ANSI only if allowed |
| `PFSENSE_OUTPUT=verbose` | every displayable line; raw syslog stays hidden |
| `PFSENSE_OUTPUT=raw` | exact collector output, no header or summary |
| Pipe / file / CI | exact output by default, for scripts, CSV and JSON |
| `NO_COLOR=1`, `TERM=dumb`, `PFSENSE_COLOR=never` | no ANSI sequences |

Colors never certify service health and never change probe exit codes.
Explicit errors stay visible even past 14 lines per section; `unknown` stays
inconclusive. Kernel OOM lines are deduplicated by precise timestamp and
grouped per minute (processes killed vs. incidents) as **historical
events**, not active failures; the minute key keeps the UTC offset (the two
`02:10` of a DST change stay distinct, a log line without offset shows
`(offset unknown)`). RFC5424 lines are classified (Unbound bind conflict,
restart notice, DNSBL Python exit, DNSSEC failure, socket buffer, CrowdSec
lifecycle) without printing raw messages; unrecognized messages show only a
count (compact) or timestamp and category (verbose). Formatting is not a
redaction mechanism: review a `raw` output before sharing it.

Validation, one step at a time:

```bash
just pfsense-console-test
just pfsense-unbound-wifi-test
bash scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh --check
PFSENSE_OUTPUT=verbose bash scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh --check
```

## CrowdSec / edge-memory read-only diagnostics

The normal `--check` path now includes the CrowdSec and pfBlockerNG evidence
needed for the 2026-10-08 OOM investigation without starting or reloading any
service.

It reports:

- CrowdSec engine PID separately from the firewall-bouncer PID;
- `crowdsec -version`, `cscli version` and installed CrowdSec package versions;
- bounded `cscli metrics` only when the engine is already running;
- redacted firewall-bouncer policy plus the last bounded warning/error lines;
- config references plus the effective `pf-scan-multi_ports` scenario policy
  (`groupby`, `distinct`, `capacity`, `leakspeed`, `blackhole`, remediation);
- streamed counts and maxima for `failed_sent`, `attempts` and `sigclosed`
  across current
  and rotated CrowdSec logs;
- only the last 30 matching backpressure lines;
- pfBlockerNG ASN Reporting state, token presence as a boolean, ASN database
  presence and the last IPinfo retry lines.

The log summarizer deliberately does **not** load all CrowdSec backpressure
lines into a shell variable. The Netgate 1100 is the constrained system being
diagnosed, so diagnostic collection must itself remain memory-bounded.

When the engine is intentionally stopped, `crowdsec_metrics=skipped_engine_stopped`
is expected. Do not restart CrowdSec merely to obtain metrics.

Interpret the `stuck ... failed_sent ... attempts` warning as an **internal
leaky-bucket delivery contention signal**, not as proof that the firewall
bouncer or LAPI network delivery failed. A sustained `max_sigclosed=0` with
`max_failed_sent` close to `max_attempts` is especially consistent with a
live bucket whose input cannot accept the event, rather than repeated bucket
destruction/recreation. CrowdSec issue
[`#1519`](https://github.com/crowdsecurity/crowdsec/issues/1519) documented the
same tight retry loop, and the upstream v1.8.1 source still uses a non-blocking
send to `bucket.In` followed by an immediate retry:
[`manager_run.go`](https://github.com/crowdsecurity/crowdsec/blob/v1.8.1/pkg/leakybucket/manager_run.go).
Record the installed version and scenario policy before considering an upgrade;
do not assume a version bump alone removes this CPU-spin path.

Also distinguish service enablement from runtime state: exporter metrics such as
`pfsense_service_enabled{name="crowdsec"} 1` show configuration enablement,
not proof that the CrowdSec engine process is running.

Since the 2026-10-27 pfSense Small cutover, the engine and LAPI run on
TrueNAS: a stopped local engine is healthy. The SSH summary prints
`WARN: crowdsec_small_mode=reverted` when the local agent, LAPI or engine is
back, and `WARN: crowdsec_bouncer=...` unless the bouncer runs against
`http://172.17.0.24:8084`. In Small mode, `service crowdsec.sh restart`
returning `1` with `crowdsec not running?` is the expected stop-only path.
The same summary flags Snort posture drift (`snort_http_memcap`,
`snort_http_inspect_7000`, `snort_download_*`); see the
[2026-11-13 incident](incidents/2026-11-13-pfsense-unbound-oom-snort-crowdsec.md).

## Netgate 1100 posture

`--check-posture` audits, and `--apply-posture` reconciles, the settings that
keep the 1 GiB appliance out of OOM and on the CrowdSec Small contract:

| Item | Desired state |
| --- | --- |
| Snort downloads | ET Open, OpenAppID detectors and AppID Open Text Rules `off` |
| Snort WAN HTTP Inspect | `http_inspect_memcap` `33554432`; `default` engine ports `snort_http_inspect` |
| Port alias | `snort_http_inspect` = `80` |
| Service Watchdog | `unbound` watched, `crowdsec` not watched |
| CrowdSec | Log Processor and Local API off, firewall bouncer on, Remote LAPI `http://172.17.0.24:8084/`, bouncer key set |
| CrowdSec runtime | no `daemon: crowdsec` supervisor left running |
| ACME certificates | every active certificate valid for at least 14 days (check only) |

A boot-environment fallback restores the `config.xml` of that environment, so
it can bring back expired ACME certificates, which HAProxy then serves on
`:443` and `:7000`. Apply mode never renews them: the renewal output prints
the Cloudflare key. Renew on pfSense with
`daemon -f /usr/local/pkg/acme/acme_command.sh renewall`. The `int` Domain
Override that the same fallback drops is repaired by `just pfsense-split-dns-apply`.

Both run `scripts/pfsense/manage-posture.php` over the same SSH contract as the
identity lifecycle (`admin@home.albandrieu.com:9922`). Apply mode:

- refuses to run while a package install or upgrade is running, because the
  install writes back the config it loaded at start;
- regenerates Snort (`sync_snort_package_config`) and restarts the WAN
  instance;
- refreshes the Service Watchdog cron;
- stops a looping CrowdSec engine supervisor before `crowdsec_resync_config`;
- never writes or prints the bouncer key, which is entered in the CrowdSec
  page from the TrueNAS LAPI.

These writes do not go through the REST API. pfREST 2.11 has no Snort,
CrowdSec or Service Watchdog endpoint, and its alias endpoint would need a
config-write key, whereas every API identity is read-only by design.

## REST API service identities

The canonical service accounts are deliberately split:

| Identity | Steady-state privileges | Purpose |
| --- | --- | --- |
| `fastapi_posture` | `api-v2-system-version-get`, `api-v2-status-services-get`, `api-v2-services-dns-resolver-settings-get`, `api-v2-system-dns-get`, `user-config-readonly` | pfSense service/DNS posture |
| `fastapi_security` | `api-v2-diagnostics-table-get`, `user-config-readonly` | exact Snort/PF table evidence |
| `pfsense_exporter` | `api-v2-status-system-get`, `api-v2-status-gateways-get`, `api-v2-status-services-get`, `user-config-readonly` | TrueNAS Prometheus pfSense metrics |

Neither identity should belong to a named privilege-bearing group such as
`admins`. The only normal group membership is pfSense's implicit `all`
group.

Keep each service user **enabled**: do not check `This user cannot login`,
because pfREST rejects API keys owned by a disabled user. API keys cannot log
into the webConfigurator or SSH; harden the users by withholding
`WebCfg - All pages`, `page-all`, shell access and every unneeded privilege.
Keep one key per identity (posture and Snort/PF telemetry are never collapsed
back into a shared `PFSENSE_API_KEY`), keep TLS verification on, and rotate any
key pasted into chat, logs, tickets or shell history. When the security
observer reaches pfSense through the same path Snort/PF may block, a transport
failure is a telemetry blind spot, not proof that Snort caused it.

The privilege ID observed on the appliance for the DNS Resolver settings GET is
`api-v2-services-dns-resolver-settings-get` (hyphens), while the REST path
remains `/api/v2/services/dns_resolver/settings` (underscore). The helper uses
the appliance privilege ID exactly. Unexpected privileges such as
`api-v2-system-restapi-version-get` are reported as drift and removed by the
explicit reconcile/finalize actions.

Audit all three service accounts, privileges and persisted key metadata without exercising
KeyAuth. The audit also instantiates the installed pfREST endpoint classes and
prints their effective GET privilege sets as `endpoint_acl ... get_privileges=...`.
Use this appliance-derived evidence to distinguish a role drift from an endpoint
ACL/package-version difference when a valid key returns HTTP 403.

Identity lifecycle commands are intentionally **workstation-only**:
the helper preflights SSH config and requires the validated management path
`admin@home.albandrieu.com:9922`. Running them from TrueNAS without that SSH
credential/config would otherwise fall back to the local username on port 22
and time out.

```bash
cd /path/to/nabla-compose
bash scripts/pfsense/diagnose-recover.sh --check-identities
```

Do not use `git cd`; `cd` is a shell builtin, not a Git command.

If either user is missing, create/reconcile both accounts to the steady-state
contract with one-line password files. Existing users keep their current
passwords; the files are used only to create missing users.

```bash
umask 077
printf '%s\n' '<posture-password>' > /tmp/pfsense-posture.password
printf '%s\n' '<security-password>' > /tmp/pfsense-security.password
printf '%s\n' '<exporter-password>' > /tmp/pfsense-exporter.password

PFSENSE_POSTURE_PASSWORD_FILE=/tmp/pfsense-posture.password \
PFSENSE_SECURITY_PASSWORD_FILE=/tmp/pfsense-security.password \
PFSENSE_EXPORTER_PASSWORD_FILE=/tmp/pfsense-exporter.password \
  bash scripts/pfsense/diagnose-recover.sh --apply-identities

rm -f /tmp/pfsense-posture.password /tmp/pfsense-security.password /tmp/pfsense-exporter.password
```

The helper sends password material only through the encrypted SSH stdin stream;
it does not put plaintext passwords on the SSH command line or in the recovery
report.

## Prometheus exporter identity

The TrueNAS Prometheus exporter uses a dedicated pfSense identity:
`pfsense_exporter`. Keep it separate from the FastAPI posture/security
identities and from the write-capable observability operator identity.

Steady-state privileges are intentionally limited to:

```text
api-v2-status-system-get
api-v2-status-gateways-get
api-v2-status-services-get
user-config-readonly
```

The lifecycle helper now supports the exporter exactly like the FastAPI
identities:

```bash
bash scripts/pfsense/diagnose-recover.sh --check-identities
bash scripts/pfsense/diagnose-recover.sh --prepare-key-rotation exporter
# create the one-time plaintext key using the pfsense_exporter Basic credentials
bash scripts/pfsense/diagnose-recover.sh --finalize-key-rotation exporter
bash scripts/pfsense/diagnose-recover.sh --check-identities
```

On TrueNAS, the runtime credential remains in
`/mnt/cpool/prometheus/secrets/pfsense-exporter.yml`. Validate it without
printing the secret or fanning out into all collectors:

```bash
sudo bash scripts/truenas/diagnose-pfsense-exporter-auth.sh
sudo PFSENSE_EXPORTER_AUTH_ENDPOINT=/api/v2/status/system \
  bash scripts/truenas/diagnose-pfsense-exporter-auth.sh
sudo PFSENSE_EXPORTER_AUTH_ENDPOINT=/api/v2/status/gateways \
  bash scripts/truenas/diagnose-pfsense-exporter-auth.sh
```

A successful rotation must produce three HTTP 200 preflights and then a
successful supervised exporter scrape. HTTP 401 means the runtime key is
rejected. HTTP 403 means authentication succeeded but a privilege, REST API
Access List rule, or Allowed Interfaces policy still denies the request.

## API-key bootstrap and rotation

`POST /api/v2/auth/key` first generates a key, then persists its hash through
pfSense configuration write logic. `User - Config: Deny Config Write`
(`user-config-readonly`) is therefore incompatible with **key creation**:
pfREST can generate and return a key while pfSense rejects the configuration
write.

Observed on 2026-10-04: after removing `User - Config: Deny Config Write`
from `fastapi_posture` while keeping `api-v2-auth-key-post`, the generated key
became visible on `/system_restapi_key.php`. This confirms the failed configuration-write gate
was `user-config-readonly`, not the key-generation privilege. The remaining
`api-v2-auth-key-post` grant is still temporary and
must be removed after rotation.

The evidence must be interpreted precisely:

- if a key for the service identity is visible in
  **System → REST API → Keys** (`/system_restapi_key.php`), that key record is
  persisted in pfSense configuration;
- a key returned once by `POST /api/v2/auth/key` is not persistence evidence
  when pfSense logged `Save config permission denied`;
- seeing a persisted key record does not recover its plaintext value. If the
  deployed plaintext produces HTTP `401`, rotate it;
- `api-v2-auth-key-post` is a **temporary rotation privilege** and must not
  remain in the steady-state role after a successful rotation.

Keep the REST API in **global read-only mode** in normal operation: posture,
exporter and Snort telemetry only need GET. Key creation is a write
(`POST /api/v2/auth/key`) and is rejected in read-only mode with
`405 ENDPOINT_METHOD_NOT_ALLOWED_IN_READ_ONLY_MODE`. Disable read-only mode only
for the duration of a rotation, re-enable it immediately after the key is
stored, then validate the allowed GETs and at least one forbidden endpoint.

The helper models the two explicit states.

Prepare one identity for rotation:

```bash
bash scripts/pfsense/diagnose-recover.sh --prepare-key-rotation posture
# or:
bash scripts/pfsense/diagnose-recover.sh --prepare-key-rotation security
```

This operation keeps only the role-specific GET privilege(s), removes
`User - Config: Deny Config Write`, and grants
`api-v2-auth-key-post`. It does **not** create a key or print a secret.

Create the key with the selected service user's own Basic credentials. For the
security identity:

```bash
curl -ksS \
  --user fastapi_security \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -X POST \
  'https://172.17.0.1:10443/api/v2/auth/key' \
  -d '{
    "length_bytes": 24,
    "hash_algo": "sha256",
    "descr": "FastAPI security observer"
  }'
```

Do not paste the response into tickets, chat or logs: `data.key` is the
one-time plaintext secret. Store it in the appropriate runtime secret source,
then confirm that the new key is visible in **System → REST API → Keys**.

Finalize the identity:

```bash
bash scripts/pfsense/diagnose-recover.sh --finalize-key-rotation security
```

Finalization refuses to proceed when pfSense has zero persisted keys for the
selected user. On success it removes `api-v2-auth-key-post` and restores `user-config-readonly`.

Then verify the steady state again:

```bash
bash scripts/pfsense/diagnose-recover.sh --check-identities
```

Finally run the KeyAuth matrix only with the new plaintext values. The expected
least-privilege contract is:

- posture GET endpoints: HTTP `200`;
- posture `diagnostics/table?id=snort2c`: HTTP `403`;
- security `diagnostics/table?id=snort2c`: HTTP `200`;
- security `status/services`: HTTP `403`.

If a rotation temporarily leaves more than one persisted key, validate the new
key first and then remove the superseded key explicitly from the REST API Keys
page. The helpers never guess which persisted key should be deleted.

## SSH is a separate capability

A successful `/api/v2/status/services` row showing `sshd` as running proves the
daemon state reported by pfSense. It does **not** prove that TCP/22 is reachable
from the workstation. Firewall policy, interface binding, or a non-default SSH
port may still make `172.17.0.1:22` time out.

Do not assume port 22. Prefer the existing workstation SSH alias. The currently
validated workstation contract resolves as `admin@home.albandrieu.com:9922`:

```bash
ssh -G home.albandrieu.com | grep -E '^(hostname|user|port) '
```

The recovery helper therefore defaults to `home.albandrieu.com` and lets
`~/.ssh/config` supply the user and port. Explicit overrides remain available:

```bash
scripts/pfsense/diagnose-recover.sh --check --target admin@home.albandrieu.com --port 9922
```

The existing posture auditor remains useful for capacity/posture regression work:

```bash
scripts/pfsense/audit-posture.sh --ssh home.albandrieu.com
```

## Mutation boundary

`--apply` requires a successful SSH control path. It only performs the bounded
recovery actions implemented by the helper: restart PHP-FPM/webConfigurator and,
when Unbound was not proven healthy, restart the resolver. Dynamic Snort or
pfBlockerNG host entries are removed only with the additional explicit
`--unblock-sources` opt-in and only for exact source-address matches.

The read-only attribution also inspects the pfSense `sshguard` table used by
Login Protection. An exact match is reported as `LOGIN_PROTECTION_MATCH`, but
the helper deliberately never deletes `sshguard` entries: authentication
lockouts require separate operator review.

Never widen firewall policy or flush PF tables merely to make a diagnostic pass.
