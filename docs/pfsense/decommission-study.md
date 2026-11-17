# Décommissionner pfSense : étude avant la bascule de la Freebox

**17/11/2026, étude seulement (`NOT_RUN`).** Les relevés ci-dessous sont faits en lecture seule sur pfSense (21:45–22:50) et sur la Freebox Ultra par son API (22:52). Rien n'est changé. La décision revient à l'opérateur ; la feuille de route est dans la [roadmap pfSense](roadmap.md#décommissionnement-de-pfsense-étude-du-1711).

## Ce que pfSense assure aujourd'hui

| Rôle | Relevé |
|---|---|
| Routage et NAT | WAN en IP publique statique ; LAN `172.17.0.1/24` ; VLAN OPT `10.20.0.1/24` ; 6 VLAN définis |
| DHCP (Kea) | LAN : plage `.100`–`.200` et 39 baux fixes. OPT : plage `.100`–`.200` et 7 baux fixes. DHCPv6 et annonces RA sur le LAN (`track6`) |
| DNS | Unbound, résolveur avec DNSSEC. Une seule délégation : `int.albandrieu.com` vers Pi-hole (`172.17.0.24`), qui fait déjà autorité sur cette zone ([propriété DNS](../dns-ingress-ownership.md)). Les baux DHCP ne sont pas enregistrés dans le DNS |
| Filtrage | 41 règles WAN, 14 LAN, 10 OPT et 25 alias, dont 9 inutilisés. 13 redirections WAN (8082, 3000, 8200, 4646, 8500, 9002, 8680, 30004, 30120, 30317, 30081, 30103, 30104), **toutes obsolètes** : aucune n'a de règle de passage active (10 désactivées, 3 orphelines), et aucun état n'est établi. Leurs cibles sont mortes (Vault, Nomad et Consul, l'ancien FreeNAS) ou ne sont pas exposées (NodePorts TrueNAS qui ne répondent que sur le LAN) |
| Ingress | HAProxy : 7 frontends, dont 2 actifs sur le WAN, `Web_HTTPS` (443) et `freenas` (7000) ; 8 certificats ACME |
| Protection | Snort sur le WAN, bouncer CrowdSec, pfBlockerNG (IP), sshguard |
| VPN | WireGuard (1 tunnel, 1 pair) et Tailscale |
| Observabilité | syslog vers Loki, softflowd vers Akvorado, ntopng, agent Zabbix |
| Divers | DynDNS Cloudflare, NTP sur OPT, 17 tâches cron, RESTAPI, Nexus |

## Ce que la Freebox Ultra peut reprendre

Relevé Freebox : firmware 4.13.6, mode bridge, Wi-Fi actif, IPv6 actif avec 8 délégations (dont 2 avec next hop). Le DHCP, les baux, les redirections, la DMZ et le VPN ne sont lisibles **qu'en mode routeur** : on ne peut rien préparer côté Freebox avant la bascule.

| Rôle | Repreneur | Faisable ? | Ce qu'on perd ou risque |
|---|---|---|---|
| Routage, NAT, IPv6 | Freebox | oui | IPv6 natif sur le LAN, plus simple qu'aujourd'hui |
| DHCP du LAN et 39 baux | DHCP Freebox, baux créés par l'API (`dhcp/static_lease`) | oui, si la Freebox accepte `172.17.0.1/24` comme adresse LAN (à tester en routeur). Sinon, il faut renuméroter tout le LAN | pas de nom d'hôte, juste un commentaire |
| VLAN OPT et ses 7 baux | aucun : la Freebox n'a qu'un réseau `/24` | non | l'isolement disparaît. Il faut fusionner dans le LAN, ou garder un petit routeur |
| DNS et split DNS | Pi-hole sur TrueNAS, distribué par le DHCP de la Freebox. Il fait déjà autorité sur `int.albandrieu.com` | oui | TrueNAS ne doit pas utiliser Pi-hole comme résolveur (boucle). Le DNS secondaire, Freebox ou public, ne connaît pas `int.*`. DNSSEC est à activer dans Pi-hole |
| Ingress HTTP | Cloudflare Tunnel (déjà en service) et Traefik sur TrueNAS (App existante), certificats en DNS-01 | oui, après migration des 2 frontends actifs | si tout passe par le tunnel, plus aucun port 443/7000 ouvert |
| DNS de TrueNAS et de Talos | aujourd'hui Unbound sur pfSense (`172.17.0.1`, épinglé dans `scripts/talos/generate-config.sh`). En A : résolveur de la Freebox ou résolveurs publics, et CoreDNS transfère `int.*` à Pi-hole | oui | en B, rien ne change |
| Adresses des nœuds Talos | baux fixes du DHCP de pfSense (`.50`, `.51`, `.52`). En A : baux fixes de la Freebox | oui | en B, rien ne change |
| 13 redirections WAN | rien à reprendre : elles ne laissent déjà rien passer | sans objet | les supprimer par script versionné. Les redirections de la Freebox n'acceptent qu'une IP source par règle, sans alias : toute ouverture future passera par Cloudflare Access/Tunnel ou Tailscale plutôt que par une redirection |
| IDS, CrowdSec, listes IP | CrowdSec avec un bouncer Traefik (couche 7) ; listes DNS dans Pi-hole | en partie | plus d'IDS réseau ni de blocage IP en bordure |
| VPN | serveur WireGuard de la Freebox, ou Tailscale sur TrueNAS (subnet router) | oui | |
| Journal pare-feu, flux | aucun | non | Akvorado et ntopng perdent leur source ; plus de journal pare-feu dans Loki |
| DynDNS | ddns-updater (App existante). L'IP publique est fixe de toute façon | oui | |
| NTP, supervision | TrueNAS (chrony) ; Freebox supervisée par son API | oui | les cibles pfSense disparaissent |

## Scénarios

- **A. Décommissionner** : la Freebox en routeur, seule. DNS, ingress et VPN passent sur TrueNAS, sans aucune redirection entrante (tunnel et Tailscale).
  - Gains : un équipement et une eMMC de moins, pas de 4200 à acheter, IPv6 natif.
  - Pertes : réseau à plat (IoT, Wi-Fi, Talos et TrueNAS sur le même `/24`), plus d'IDS ni de journal pare-feu, plus de dépendance à TrueNAS. L'objectif « segmentation en VLAN » de la roadmap sécurité devient impossible ; « admin par VPN seul » reste faisable avec Tailscale.
- **B. Freebox en routeur avec pfSense derrière** (le 4200, en DMZ) : on garde tout, la fuite de l'IP publique au démarrage à froid disparaît, et le Wi-Fi de la Freebox devient sûr. Le prix : un double NAT ([procédure](runbooks/freebox-router-mode.md)).
- **C. Statu quo** : bridge, et le 4200 remplace le 1100.

**Recommandation.** La phase 0 ci-dessous sert dans les trois scénarios, et elle réduit l'exposition. La faire d'abord, puis trancher entre A et B. **Ne pas commander le 4200 avant ce choix.** Je ne retiendrais A que si un réseau à plat est acceptable : la Freebox ne sait isoler que son Wi-Fi invité.

## Points techniques

- **Migrer le DHCP** : un script `plan`/`apply` lit les baux fixes Kea de pfSense par SSH et les crée par l'API Freebox. Les MAC ne vont jamais dans le dépôt, qui est public. Comme la Freebox ne répond qu'en routeur, l'`apply` se fait juste après la bascule.
- **Migrer le split DNS** : il n'y a qu'une délégation (`int.albandrieu.com` vers Pi-hole). La migration consiste à distribuer Pi-hole comme DNS principal, ce qu'on peut faire dès la phase 0 avec le DHCP de pfSense.
- **Garder l'IP publique** : elle est attachée à la ligne Free. En bridge, la Freebox la distribue en DHCP, et en routeur elle la porte elle-même. Les noms Cloudflare et le DynDNS ne changent pas.
- **App Freebox** : réduire ses droits au strict nécessaire, c'est-à-dire décocher Explorateur, VM, Appels, Contacts, Téléchargements, TV et PVR. Ne cocher « Modification des réglages » qu'au moment de la bascule.
