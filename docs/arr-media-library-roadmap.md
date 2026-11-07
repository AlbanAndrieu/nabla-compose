# Bibliothèque média \*arr — roadmap d'installation et d'anonymisation

> Mise à jour : **7 novembre 2026**. Document d'architecture **canonique** pour la
> pile \*arr (acquisition, organisation, consommation), la frontière VPN des
> téléchargements et la stratégie DNS associée. Il remplace les sections
> ARR/VPN/stockage de [`arr-security-integration-roadmap.md`](arr-security-integration-roadmap.md),
> qui ne conserve que CrowdSec/Traefik, Dozzle et les MCP sécurité. Les priorités
> courantes restent indexées dans [`roadmap.md`](roadmap.md).
>
> Ce document **n'autorise aucune mutation**. Chaque phase exige une sauvegarde,
> un plan en lecture seule, l'accord de l'opérateur et une preuve de retour
> arrière (voir les règles de `roadmap.md`).

## 1. Synthèse des recommandations

1. **VPN par namespace, pas par hôte ni par pfSense.** Un conteneur Gluetun
   (WireGuard) partage sa pile réseau avec **qBittorrent seulement**
   (`network_mode: service:gluetun`). Le pare-feu de Gluetun assure le kill
   switch. Les autres services TrueNAS et le LAN ne sont pas touchés.
2. **DNS over TLS émis dans le tunnel.** Le résolveur intégré de Gluetun
   (DoT vers Quad9) ne sort que par l'interface VPN. Ni pfSense, ni Pi-hole, ni
   les résolveurs de secours de TrueNAS ne voient les requêtes du client torrent.
   Pas de forwarder DNS supplémentaire sur TrueNAS.
3. **Indexeurs via le proxy HTTP de Gluetun.** Prowlarr reste sur le réseau
   Docker normal et passe toutes ses requêtes externes par le proxy HTTP
   authentifié de Gluetun. Si le VPN tombe, les recherches échouent
   (fail-closed) au lieu de partir par le WAN.
4. **Le reste hors VPN.** Radarr, Sonarr, Bazarr, Seerr, le serveur média,
   Traefik, Pi-hole et les autres services gardent la sortie WAN et le DNS
   pfSense/Unbound actuels ([contrat DNS](dns-ingress-ownership.md)).
5. **Aucune interface \*arr publique.** Traiter d'abord les sept noms publics
   hérités (§2.3). L'accès LAN passe par Traefik `*.int.albandrieu.com`. L'accès
   distant passe uniquement par Cloudflare Access (Seerr) ou par un VPN d'accès.

## 2. État existant

Niveaux de preuve : `CODED` (dépôt), `OBSERVED` (mesure datée), `NOT_VERIFIED`.

### 2.1 Source Servers@Home analysée

Pages lues le 7 novembre 2026 : [Arr Stack](https://wiki.serversatho.me/en/arr-stack),
[Install Instructions](https://wiki.serversatho.me/InstallInstructions),
[Folder Structure](https://wiki.serversatho.me/Folder-Structure),
[Overview Map](https://wiki.serversatho.me/OverviewMap) et
[qBittorrent](https://wiki.serversatho.me/qBittorrent).

**À reprendre :**

- l'ordre d'installation : stockage, VPN, client torrent, Radarr/Sonarr,
  Prowlarr, profils de qualité, serveur média, Seerr, Bazarr ;
- un **seul dataset** `media` avec des sous-répertoires (pas de sous-datasets),
  pour que les hardlinks et les déplacements atomiques fonctionnent ;
- un client torrent lié à l'interface VPN, avec DNS dans le tunnel ;
- libtorrent 2.x et le type d'E/S disque « POSIX-compliant » sur ZFS.

**À ne pas reprendre :**

- le script `arr-complete.sh`, exécuté en root via `wget … && bash`. Il crée et
  démarre des stacks implicitement, utilise des images `latest` et ajoute
  Dockge et Watchtower, en concurrence avec `apps/`, Renovate et
  [`apps/watchtower`](watchtower-service-units.md) ;
- les permissions `root:apps 770` et le compte commun `admin`/`changeme`
  partagé par toutes les applications ;
- la variante WireGuard générique : la protection anti-fuite y dépend d'une
  ligne `PostUp` iptables recopiée à la main. Elle ajoute aussi des routes LAN
  larges (`10/8`, `172.16/12`, `192.168/16`, `100.64/10`) ;
- le conseil de remplacer le DNS du fournisseur par `1.1.1.1` en clair. Le DoT
  dans le tunnel est préférable (§5) ;
- le catalogue d'environ 45 outils de la page d'index : c'est un outil de
  découverte, pas une liste d'installation.

### 2.2 nabla-compose (`CODED`)

- **Aucun** `apps/<service>/compose.yml` pour une application \*arr, un client
  torrent, Gluetun ou un serveur média.
- Les briques réutilisables existent : `apps/traefik`, `apps/pihole`
  (avec `pihole-dns-sync`), `apps/dozzle`, `apps/watchtower`, `apps/crowdsec`,
  `apps/gatus`, `apps/homarr`, et `apps/suricata` en `network_mode: host` sur
  `br0` (utile comme détecteur de fuite, §8 P6).
- [`truenas-file-structure.sh`](../truenas-file-structure.sh) est un ancien
  générateur dérivé de Servers@Home. Il est à **geler** :
  - images `latest` ;
  - `VPN_PROVIDER=generic` combiné à `VPN_AUTO_PORT_FORWARD=true` : l'image
    hotio ne gère le port automatique qu'avec `proton` ou `pia` ;
  - `VPN_FIREWALL_TYPE` a été retiré de l'image ;
  - Prowlarr n'a ni `PUID` ni `PGID` ;
  - `toparr` tourne avec `pid: host`, `SYS_ADMIN` et `SYS_PTRACE`.
- `catalog/homelab-services.json` déclare lidarr, prowlarr, radarr, sabnzbd,
  sonarr et transmission avec `external: false`, **mais** chacun avec un
  `tunnelUrl` `https://<id>.albandrieu.com`.
- `terraform/cloudflare/tunnel.tofu` route `emby.albandrieu.com` vers
  `172.17.0.24:8096`. C'est la seule route média codée.
- `config/truenas/restore-optional-apps.txt` liste les Apps TrueNAS natives
  `bazarr`, `cleanuparr`, `emby`, `lidarr`, `plex`, `prowlarr`, `radarr`,
  `readarr`, `sonarr`, `tracearr`, `transmission`, `whisparr`, `wizarr`, ainsi
  que `arti`, `i2p`, `tailscale`, `squid` et `three-proxy`.
- [`roadmap.md`](roadmap.md) garde un diagnostic P0 ouvert sur `lidarr`.

### 2.3 Exposition publique observée (`OBSERVED`, 7 novembre 2026)

Mesure faite depuis un client externe situé hors de France : DNS via DoH, puis
`HEAD /` en HTTPS.

| Noms `*.albandrieu.com` | DNS public | Réponse HTTPS |
| --- | --- | --- |
| `radarr`, `sonarr`, `prowlarr`, `lidarr`, `transmission`, `sabnzbd`, `emby` | A proxifiés Cloudflare. Ce sont des enregistrements explicites : un nom aléatoire ne résout pas. | `403` texte servi par Cloudflare, **sans** redirection Cloudflare Access |
| `gatus` (témoin) | A proxifiés Cloudflare | `302` vers Cloudflare Access |

**Interprétation (risque potentiel) :** sept noms média sont publiés. Le `403`
ressemble à une règle WAF (pays, IP ou bot), pas à une politique Access. Il est
donc possible qu'un client situé en France atteigne l'origine. Ce point est
`NOT_VERIFIED` depuis la France et doit être traité en P0 (§8).

### 2.4 TrueNAS (`NOT_VERIFIED`)

L'état runtime des Apps natives n'a pas été relu pour ce document (pas d'accès
LAN). Dernières observations documentées :

- Lidarr est en diagnostic P0 ;
- Transmission et Emby étaient arrêtés lors de la revue du 13 septembre ;
- le dataset `cpool/sabnzbd` est vide (candidat de revue).

Seul le pool `cpool` est documenté. L'emplacement de la bibliothèque (pool
actuel ou pool HDD dédié) est la décision D3.

## 3. Matrice des services

| Service | Rôle | Servers@Home | Nabla aujourd'hui | Décision | Phase |
| --- | --- | --- | --- | --- | --- |
| Gluetun | passerelle VPN WireGuard, DNS DoT, proxy HTTP | variante | analyse seulement | **Ajouter** | P2 |
| qBittorrent | client BitTorrent | oui (hotio + WireGuard) | script legacy | **Ajouter**, dans le namespace Gluetun | P2 |
| Transmission | client BitTorrent | non | App native et DNS public | **Retirer** (doublon, hors VPN) | P0 |
| SABnzbd | client Usenet | oui | catalogue, DNS public, dataset vide | **Différer** (seulement avec un abonnement Usenet, D4) | — |
| Prowlarr | gestion des indexeurs | oui | App native | **Migrer**, derrière le proxy Gluetun | P3 |
| FlareSolverr / Trawl / Byparr | contournement Cloudflare des indexeurs | oui (Trawl) | script legacy | **Seulement si un indexeur l'exige** (§6.3) | P3 |
| Radarr | films | oui | App native | **Migrer** | P4 |
| Sonarr | séries | oui | App native | **Migrer** | P4 |
| Lidarr | musique | hors cœur | App native, diagnostic P0 | **Migrer après le diagnostic** | P4 |
| Readarr | livres | remplacé par Chaptarr | App native | **Retirer** (projet arrêté par ses mainteneurs). Chaptarr : à évaluer plus tard | P0 |
| Whisparr | — | non | App native | hors périmètre, décision de l'opérateur | — |
| Recyclarr / Profilarr | profils de qualité TRaSH | Profilarr | Profilarr (legacy), Recyclarr (roadmap de septembre) | **Recyclarr** : configuration YAML versionnée et revue en PR | P4 |
| Bazarr | sous-titres | oui | App native | **Migrer** | P5 |
| Jellyfin / Emby / Plex | serveur média | Emby / Jellyfin | Emby et Plex natifs, Jellyfin legacy | **Décision D2** ; Jellyfin recommandé | P5 |
| Seerr | demandes | oui | script legacy | **Ajouter** après D2 | P5 |
| Unpackerr | extraction des `.rar` | oui | — | seulement si des releases archivées sont observées | P6 |
| Cleanuparr | torrents bloqués, faux ou malveillants | — | App native | après stabilisation de qBittorrent | P6 |
| Wizarr, Tracearr | invitations, statistiques de lecture | oui | Apps natives | seulement en cas de partage avec d'autres utilisateurs | P6 |
| Tdarr | transcodage | oui | — | après mesure CPU, GPU et E/S | P6 |
| Exportarr / Scraparr | métriques Prometheus | — | roadmap de septembre | **un seul des deux** | P6 |
| Dockge, Watchtower de Servers@Home | gestion des stacks, mises à jour | oui | `apps/`, Renovate, `apps/watchtower` | **Ne pas ajouter** | — |
| arti, i2p (Tor) | anonymat | — | Apps natives | **Ne jamais** y faire passer BitTorrent : fuites d'IP par le protocole, charge imposée au réseau Tor | — |

## 4. Architecture cible

```text
                               Internet
                                  ▲
                 WireGuard (UDP)  │  seul flux d'acquisition visible par
                                  │  le FAI et par pfSense
┌──────────────────────── TrueNAS 172.17.0.24 (br0) ─────────────────────────┐
│                                                                             │
│  namespace « acquisition » (projet Compose apps/media-acquisition)          │
│  ┌──────────────────────────────────────────────────┐                       │
│  │ gluetun     interface VPN + kill switch          │◄─ proxy HTTP :8888 ───┼─ prowlarr
│  │             DNS 127.0.0.1 → DoT Quad9 via VPN    │   (réseau arr)        │  (+ flaresolverr si requis)
│  │ qbittorrent WebUI :8080, liée à l'interface VPN  │◄─ API :8080 ──────────┼─ radarr / sonarr / lidarr
│  └──────────────────────────────────────────────────┘                       │
│                                                                             │
│  réseau Docker « arr », hors VPN : prowlarr, radarr, sonarr, lidarr,        │
│  bazarr, recyclarr, seerr, serveur média                                    │
│      DNS : Docker → TrueNAS → pfSense Unbound (inchangé)                    │
│                                                                             │
│  /mnt/cpool/media ── monté en /data ── qbittorrent, *arr, serveur média (ro)│
└─────────────────────────────────────────────────────────────────────────────┘
      Traefik *.int.albandrieu.com (LAN) ─► interfaces ; aucune route *arr publique
```

Règles d'architecture :

- Seuls `gluetun` et `qbittorrent` partagent le namespace. Le §6.3 explique
  pourquoi Prowlarr et FlareSolverr n'y entrent pas par défaut.
- `network_mode: service:` ne fonctionne qu'à l'intérieur d'un même projet
  Compose. Gluetun et qBittorrent forment donc **une** unité de déploiement :
  `apps/media-acquisition/`. Les autres services suivent `apps/<service>/`,
  avec métadonnées `x-nabla` et relations selon
  [`nabla-service-catalog`](../.agents/skills/nabla-service-catalog/SKILL.md).
- Si Gluetun redémarre seul, qBittorrent perd sa pile réseau. Il faut donc
  `depends_on: {gluetun: {condition: service_healthy, restart: true}}`, et
  Renovate comme Watchtower doivent mettre à jour l'unité entière, jamais
  Gluetun isolément.

## 5. Stratégie DNS

### 5.1 Trois zones, trois chemins

| Zone | Clients | Résolveur | Transport | Qui voit les requêtes |
| --- | --- | --- | --- | --- |
| Acquisition | qBittorrent (trackers, DHT), proxy HTTP Gluetun (requêtes de Prowlarr) | DNS intégré de Gluetun | DoT vers Quad9, **dans** le tunnel | Quad9, qui ne voit que l'IP de sortie VPN. Ni le FAI, ni pfSense, ni Pi-hole. |
| Homelab | Radarr, Sonarr, Bazarr, Seerr, serveur média, autres conteneurs, TrueNAS | DNS Docker, puis pfSense Unbound `172.17.0.1` ; `int.albandrieu.com` vers Pi-hole | récursif depuis le WAN (inchangé) | Serveurs autoritatifs et FAI : noms de domaine des API de métadonnées. Les titres restent dans HTTPS. |
| Clients LAN | postes, nœuds Talos… | pfSense Unbound | inchangé | inchangé |

### 5.2 Pourquoi pas un forwarder DNS sur TrueNAS ou pfSense

- **Le DoT seul n'anonymise pas.** Il chiffre la requête vis-à-vis du FAI, mais
  le résolveur public voit toujours l'IP WAN du foyer. Le DoT **émis depuis le
  tunnel** masque les deux. Le namespace Gluetun l'obtient sans composant
  supplémentaire.
- **Un forwarder sur TrueNAS** (Unbound ou AdGuard en conteneur) ajouterait un
  saut en clair entre conteneurs et un point de panne partagé. Si son amont ne
  sort pas par le VPN, il révèle l'IP WAN au résolveur. Il recréerait aussi la
  dépendance circulaire TrueNAS ↔ DNS hébergé sur TrueNAS, déjà proscrite.
- **Passer pfSense Unbound en forwarding DoT** changerait le contrat validé
  (`Forwarding Mode: disabled`) pour tout le LAN. Cela n'améliore pas
  l'anonymat des téléchargements, qui ne passent pas par Unbound. Unbound sur
  pfSense a déjà eu des incidents mémoire
  ([diagnostic](../scripts/pfsense/diagnose-unbound-crash-memory.sh)) : ne pas
  le placer dans le chemin critique d'un nouveau service.
- **Split DNS.** Le seul découpage nécessaire existe déjà
  (`int.albandrieu.com` → Pi-hole). Le namespace d'acquisition n'a besoin
  d'aucun nom privé, donc d'aucune exception DNS vers le LAN. C'est une autre
  raison de laisser Prowlarr hors du namespace : il devrait sinon résoudre les
  noms Docker ou LAN de Radarr et Sonarr.

### 5.3 Réglages DNS de Gluetun

Référence : [options DNS de Gluetun](https://github.com/qdm12/gluetun-wiki/blob/main/setup/options/dns.md).
À revérifier sur la version épinglée.

- `DNS_UPSTREAM_RESOLVER_TYPE=dot` et `DNS_UPSTREAM_RESOLVERS=quad9` (défaut :
  `cloudflare`) ;
- `DNS_UPSTREAM_IPV6=off` et `BLOCK_MALICIOUS=on` ;
- **ne jamais définir** `DNS_UPSTREAM_PLAIN_ADDRESSES` vers Pi-hole, pfSense
  ou une IP de bridge. La documentation de Gluetun prévient que le DNS peut
  alors sortir du tunnel ;
- alternative acceptable : le DNS du fournisseur VPN dans le tunnel, si ce
  fournisseur le recommande. Cela évite un tiers supplémentaire.

### 5.4 Option LAN séparée (D6, non requise ici)

Si l'objectif devient de cacher au FAI le DNS de **tout** le LAN : passer
pfSense Unbound en Forwarding Mode, activer « Use SSL/TLS for outgoing DNS
Queries to Forwarding Servers » vers `dns.quad9.net:853`, et conserver la
Domain Override `int.albandrieu.com` ainsi que la validation DNSSEC.

Le compromis : la visibilité du FAI est remplacée par la confiance en Quad9. À
instruire séparément avec le
[skill pfSense](../.agents/skills/pfsense-api-debugging/SKILL.md).

Les résolveurs de secours en clair de TrueNAS (`9.9.9.9`, `1.1.1.1`) restent en
place : ils font partie du contrat de reprise et ne concernent pas la zone
acquisition.

## 6. Stratégie VPN

### 6.1 Options comparées

| Option | Isolation | Effet sur les autres services | Kill switch | Complexité | Verdict |
| --- | --- | --- | --- | --- | --- |
| A. Gluetun + `network_mode: service:gluetun` sur TrueNAS | namespace réseau du conteneur | aucun | pare-feu Gluetun : tout est bloqué hors tunnel, y compris avant sa montée | faible, pattern standard | **Recommandée** |
| B. WireGuard intégré à l'image qBittorrent (hotio) | même isolation, pour qBittorrent seul | aucun | nftables de l'image | faible | acceptable pour un seul conteneur, mais pas de proxy pour Prowlarr |
| C. Client WireGuard sur pfSense + routage par politique (VLAN dédié ou IP alias TrueNAS) | segment réseau | modifie le routeur de tout le foyer | règles PF et passerelle par défaut bloquée | élevée : VLAN ou macvlan sur TrueNAS, vues Unbound | **Non retenue** : touche l'équipement critique pour un bénéfice local |
| D. Tor (`arti`, `i2p`) | — | — | — | — | **Exclue** pour BitTorrent |
| E. VPN sur tout l'hôte TrueNAS | — | casse Cloudflare Tunnel, l'accès LAN et les mises à jour | — | — | **Exclue** |

### 6.2 Fournisseur (décision D1)

Critères : WireGuard, port forwarding (nécessaire pour être joignable et
partager), politique no-log vérifiable, prise en charge native par Gluetun
([port forwarding Gluetun](https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/vpn-port-forwarding.md)).

| Fournisseur | Port forwarding | Intégration Gluetun | Remarque |
| --- | --- | --- | --- |
| ProtonVPN Plus | dynamique (NAT-PMP), sur les serveurs P2P | native : `VPN_PORT_FORWARDING=on`, `PORT_FORWARD_ONLY=on` | déjà évalué en septembre ; le port change, il faut le synchroniser dans qBittorrent (§6.3) |
| AirVPN | statique, attribué dans l'espace client | fournisseur pris en charge, port ouvert par `FIREWALL_VPN_INPUT_PORTS` | choix de Servers@Home ; un port fixe supprime l'appel d'API vers qBittorrent |
| Mullvad | supprimé en 2023 | native | bon anonymat de paiement, mais client non joignable : partages de mauvaise qualité |
| Private Internet Access | dynamique | native | juridiction des États-Unis |

**Recommandation :** ProtonVPN, cohérent avec l'analyse de septembre et doté
d'audits no-log publiés. Choisir AirVPN si l'on préfère un port statique et
supprimer la synchronisation de port (§6.3). Si l'anonymat vis-à-vis du
fournisseur compte, choisir un moyen de paiement non nominatif ; à vérifier au
moment de la souscription.

### 6.3 Synchronisation du port et accès localhost

Avec Proton, Gluetun exécute `VPN_PORT_FORWARDING_UP_COMMAND`. Cette commande
appelle l'API de qBittorrent sur `127.0.0.1:8080`, ce qui exige l'option
« Bypass authentication for clients on localhost ». Le modèle de commande
renseigne aussi l'interface VPN (`{{VPN_INTERFACE}}`) dans qBittorrent.

**Conséquence :** tout processus du namespace pilote qBittorrent sans mot de
passe, y compris l'option « exécuter un programme externe ». Cela revient à
exécuter des commandes avec un accès en écriture à `/data`. D'où les règles
suivantes :

- seuls `gluetun` et `qbittorrent` vivent dans le namespace ;
- FlareSolverr, un Chromium sans interface qui charge des pages d'indexeurs non
  fiables, n'entre **jamais** dans ce namespace tant que le bypass localhost est
  actif. S'il devient nécessaire derrière le VPN, choisir l'une de ces options :
  - port statique (AirVPN) et bypass désactivé ;
  - synchronisation par un conteneur auxiliaire authentifié ;
  - second namespace Gluetun dédié à l'indexation ;
- `VPN_PORT_FORWARDING_DOWN_COMMAND` remet le port à 0. C'est le contournement
  documenté par Gluetun pour un bogue de qBittorrent.

### 6.4 Comportement fail-closed attendu

- Tunnel absent : qBittorrent n'a aucune sortie, le pare-feu Gluetun bloque
  tout.
- Gluetun arrêté : le namespace disparaît, qBittorrent n'a plus de réseau et ne
  redémarre qu'avec un Gluetun sain.
- Proxy `:8888` indisponible : Prowlarr est en erreur, sans repli direct.
- IPv6 désactivé dans le namespace. Si le WAN ou le LAN fournit de l'IPv6, une
  fuite IPv6 est le premier scénario à tester (§9).

## 7. Stockage et permissions

Un dataset unique garantit les hardlinks et les déplacements atomiques. Les
noms suivent [TRaSH Guides](https://trash-guides.info/File-and-Folder-Structure/)
(`/data/torrents`, `/data/media`), avec `library` à la place de `media` pour
éviter `/mnt/cpool/media/media`.

```text
/mnt/cpool/media            dataset preset APPS (ou pool HDD : décision D3), apps:apps (568:568)
├── torrents/               écrit par qBittorrent
│   ├── incomplete/
│   └── movies/  tv/  music/        catégories qBittorrent
└── library/                écrit par Radarr, Sonarr, Lidarr et Bazarr ; lu par le serveur média
    └── movies/  tv/  music/
```

- **Montages :** le même `/mnt/cpool/media:/data` dans qBittorrent, Radarr,
  Sonarr, Lidarr et Bazarr. Le serveur média monte
  `/mnt/cpool/media/library:/data/library:ro`.
- **Configuration et secrets :** les configurations vont dans
  `/mnt/cpool/<service>` (preset APPS) et les secrets dans
  `/mnt/cpool/secrets/runtime/<service>/`
  ([disposition runtime](truenas-runtime-layout.md)).
- **ZFS :** `recordsize=1M`, `compression=lz4`, `atime=off`. Côté qBittorrent :
  libtorrent 2.x et le type d'E/S disque « POSIX-compliant ». À valider par une
  mesure ARC et mémoire (P1 performance de `roadmap.md`).
- **Snapshots :** la bibliothèque peut être retéléchargée et les torrents
  changent sans cesse. Pas de tâche fréquente sur `cpool/media`, pour éviter la
  croissance déjà constatée ([politique snapshots](truenas-zfs-snapshot-policy.md)).
  Les configurations `cpool/<arr>` rejoignent la tâche « Small configuration »,
  en plus des sauvegardes intégrées aux applications \*arr.
- **Permissions :** `PUID=568`, `PGID=568`, `UMASK=002`, ACL preset APPS. Pas de
  `root:apps 770`. L'image Seerr tourne avec l'UID 1000 : à vérifier sur la
  version épinglée.
- **Test hardlink obligatoire :** `stat -c '%h %i'` sur le fichier dans
  `torrents/` et dans `library/` doit donner le même inode et 2 liens.

## 8. Roadmap par phases

### P0 — Décisions et réduction de l'exposition existante (aucune installation)

1. **Exposition publique média (§2.3).** Depuis un client situé en France (par
   exemple en 4G) :
   - relever la réponse des sept noms ;
   - identifier dans Cloudflare la règle qui produit le `403` ;
   - avec le plan OpenTofu du P0 Cloudflare de [`roadmap.md`](roadmap.md),
     supprimer les enregistrements DNS et les routes Tunnel de ces services
     `external=false`, ou les placer derrière Access ;
   - retirer les `tunnelUrl` correspondants du catalogue et régénérer les
     contrats.

   **Clôture :** aucun nom \*arr ou torrent ne résout publiquement, ou un `302`
   Access est vérifié depuis un client externe situé en France. Le plan
   OpenTofu est appliqué avec approbation.
2. **Emby et Plex via Cloudflare Tunnel.** Vérifier la politique Access de
   `emby.albandrieu.com`. Vérifier aussi que les conditions de service de
   Cloudflare autorisent le streaming vidéo via Tunnel/CDN. Pour le streaming
   distant, préférer un VPN d'accès (WireGuard sur pfSense, ou Tailscale,
   actuellement arrêté). Décision D5.
3. **Inventaire TrueNAS en lecture seule.** Avec `midclt call app.query`,
   relever pour chaque App de §2.4 : nom, état, version, stockage (ixVolume ou
   hostPath) et ports. Exporter la sauvegarde intégrée de Prowlarr, Radarr,
   Sonarr, Lidarr et Bazarr (System → Backup) vers `cpool/backup`. Noter les
   root folders et les clients de téléchargement configurés.

   **Clôture :** tableau daté dans un runbook ; chaque sauvegarde restaurée avec
   succès dans un conteneur jetable.
4. **Retraits.** Transmission (client hors VPN, doublon) et Readarr (projet
   arrêté) restent arrêtés, puis sont retirés après sauvegarde. Vérifier dans
   leurs journaux si des téléchargements ont eu lieu hors VPN. Si oui, l'IP WAN
   a été exposée aux pairs : c'est une information, aucune correction a
   posteriori n'est possible.
5. **Geler `truenas-file-structure.sh`.** Ajouter une bannière « ne pas
   exécuter » ou le retirer au profit de `apps/`.
6. **Décisions de l'opérateur :**
   - D1 : fournisseur VPN ;
   - D2 : serveur média ;
   - D3 : pool et volumétrie de la bibliothèque ;
   - D4 : Usenet, oui ou non ;
   - D5 : accès distant ;
   - D6 : DoT pour tout le LAN (optionnel).

### P1 — Stockage

1. Créer `cpool/media` (ou le dataset sur le pool D3) via le middleware TrueNAS,
   avec le preset APPS, les propriétés ZFS et l'arborescence du §7.
2. Ne créer aucune tâche de snapshot fréquente. Si une politique est retenue, la
   déclarer dans `config/truenas/snapshot-tasks.json`.
3. Tester un hardlink entre `torrents/` et `library/` depuis deux conteneurs
   jetables qui montent `/data`.

**Clôture :** inode identique, `UMASK=002` effectif, et
`scripts/truenas/bootstrap-repository-runtime.sh --check` sans écart.

### P2 — Frontière VPN : Gluetun + qBittorrent

1. **Secrets.** La clé privée WireGuard et les identifiants du proxy HTTP et de
   la WebUI vont dans Vaultwarden, puis dans
   `/mnt/cpool/secrets/runtime/media-acquisition/` (mode `0600`). Jamais dans
   Git ni dans `apps/`.
2. **Compose.** Créer `apps/media-acquisition/compose.yml` à partir de
   l'esquisse du §10 : images épinglées par digest et suivies par Renovate,
   métadonnées `x-nabla` et relations, catalogue régénéré.
3. **Réglages qBittorrent :**
   - interface réseau = interface VPN de Gluetun ;
   - UPnP, NAT-PMP et LSD désactivés ;
   - chiffrement « Require » et mode anonyme ;
   - « Excluded file names » : `*.exe`, `*.scr`, `*.lnk`, `*.bat`, `*.cmd`,
     `*.com`, `*.msi`, `*.vbs`, `*.ps1`, `*.js` ;
   - aucun programme externe ;
   - WebUI authentifiée, avec validation de l'en-tête Host et protection CSRF ;
   - catégories `movies`, `tv`, `music` vers `/data/torrents/<catégorie>` ;
     fichiers incomplets dans `/data/torrents/incomplete`.
4. **Port forwarding.** Avec Proton : commandes UP et DOWN de Gluetun. Avec
   AirVPN : `FIREWALL_VPN_INPUT_PORTS` et port fixe dans qBittorrent.
5. **Exposition de la WebUI.** Via Traefik, `qbittorrent.int.albandrieu.com`,
   avec les labels sur `gluetun`. Pas de port publié sur l'hôte, sauf un accès
   LAN de secours documenté.

**Clôture :** **toute** la batterie du §9 est verte et consignée avec la date et
le SHA déployé.

### P3 — Indexation : Prowlarr

1. Déployer `apps/prowlarr/` sur le réseau `arr` et restaurer la sauvegarde P0.
2. Dans Settings → General → Proxy : HTTP vers `gluetun:8888`, avec
   identifiants. Activer « Bypass proxy for local addresses », avec la liste de
   contournement `radarr,sonarr,lidarr,*.int.albandrieu.com`.
3. FlareSolverr ou Byparr seulement si un indexeur l'exige, avec les
   contraintes du §6.3.
4. Connecter Radarr, Sonarr et Lidarr en « Full Sync ». Les recherches et les
   téléchargements de `.torrent` passent alors par Prowlarr, donc par le proxy.

**Clôture :**

- une recherche dans Prowlarr réussit ;
- pendant cette recherche, le journal Unbound de pfSense et une capture sur
  `br0` ne montrent ni requête DNS ni connexion directe vers les domaines
  d'indexeurs ;
- Gluetun arrêté, la recherche échoue, sans repli direct.

### P4 — Organisation : Radarr, Sonarr, Lidarr, Recyclarr

1. **Migration, une App à la fois :**
   1. arrêter l'App native ;
   2. déployer la version Compose sur le même port hôte ;
   3. restaurer la sauvegarde ;
   4. remapper les root folders vers `/data/library/...` avec l'éditeur de
      masse ;
   5. valider ;
   6. retirer l'App native après une période d'observation.
2. **Réglages Radarr et Sonarr :**
   - client de téléchargement `gluetun:8080`, avec une catégorie dédiée ;
   - « Use hardlinks instead of copy » activé ;
   - authentification Forms obligatoire ;
   - rapports d'usage anonymes désactivés.
3. **Recyclarr.** Versionner `apps/recyclarr/config/recyclarr.yml` (profils
   TRaSH, dont les formats français MULTi, VFF et VOSTFR, à valider). Clés API
   dans les secrets. Exécution planifiée.
4. **Lidarr.** Seulement après la clôture du diagnostic P0 de `roadmap.md`.
5. **Option N3 (décision).** Faire passer aussi Radarr et Sonarr (métadonnées)
   par le proxy Gluetun. Non recommandé par défaut : les API publiques limitent
   le débit ou affichent des captchas aux IP VPN, et l'interface dépendrait du
   VPN.

**Clôture :** un parcours complet (recherche, qBittorrent, hardlink,
bibliothèque) avec un inode partagé et un partage (seed) continu.

### P5 — Consommation : serveur média, Bazarr, Seerr

1. **Serveur média (D2).** Jellyfin est recommandé : pas de compte tiers
   obligatoire, alors que Plex exige un compte plex.tv. Valider le transcodage
   matériel via `/dev/dri` (iGPU déjà utilisé par `toparr`). Bibliothèque en
   lecture seule.
2. **Bazarr.** Sous-titres FR et EN. Les comptes des fournisseurs de
   sous-titres vont dans les secrets. Proxy optionnel (N3).
3. **Seerr.** Connecté au serveur média, à Radarr et à Sonarr. C'est le seul
   candidat à un accès distant via Cloudflare Access : aucune API \*arr n'est
   exposée.
4. **Emby et Plex natifs.** Les migrer ou les retirer selon D2. Ne pas faire
   tourner trois serveurs média sans raison.

**Clôture :** lecture locale et transcodage mesurés. Accès distant conforme à D5
et testé depuis l'extérieur, avec un test négatif sans authentification.

### P6 — Exploitation et compléments

- **Supervision.** Gatus (`/ping` des \*arr ; serveur de contrôle Gluetun en
  interne seulement). Prometheus via Exportarr **ou** Scraparr. Dozzle via le
  proxy du socket Docker, déjà en roadmap.
- **Détection de fuite par Suricata.** Vérifier que la catégorie ET Open P2P
  est chargée sur `br0`. Le trafic légitime du namespace est du WireGuard
  chiffré : toute signature BitTorrent vue en clair sur `br0` est une fuite.
- **Compléments, un par un et avec justification :** Cleanuparr, Unpackerr,
  Tdarr, Wizarr, Tracearr.
- **Mises à jour.** Renovate met à jour Gluetun et qBittorrent dans la même PR.
  Watchtower traite `media-acquisition` comme une seule unité
  ([unités Watchtower](watchtower-service-units.md)).

## 9. Tests d'acceptation de l'anonymat (P2, P3)

Exécuter depuis TrueNAS, sans afficher de secret. Ne jamais publier l'IP WAN :
consigner seulement « égale » ou « différente ».

| # | Test | Résultat attendu |
| --- | --- | --- |
| 1 | IP publique vue du namespace : `docker exec qbittorrent curl -fsS https://ipinfo.io/ip`, comparée à l'IP WAN de pfSense | différente ; pays = serveur VPN |
| 2 | IPv6 : `docker exec qbittorrent curl -6 -fsS -m 5 https://ipv6.icanhazip.com` | échec |
| 3 | Kill switch : bloquer temporairement l'endpoint VPN sur pfSense, puis relancer le test 1 | aucune sortie, aucun repli WAN |
| 4 | DNS : `docker exec qbittorrent cat /etc/resolv.conf`, puis `nsenter -t "$(docker inspect -f '{{.State.Pid}}' gluetun)" -n tcpdump -ni eth0 'port 53 or port 853'` pendant l'ajout d'un torrent | résolveur `127.0.0.1` ; aucun paquet DNS sur `eth0`, seul le flux WireGuard |
| 5 | Fuite BitTorrent : magnet de détection d'[ipleak.net](https://ipleak.net/) (« Torrent Address detection ») | seule l'IP VPN apparaît |
| 6 | Port forwarding : le port publié par Gluetun est égal au `listen_port` de qBittorrent ; statut « connectable » | toujours vrai après une reconnexion forcée |
| 7 | Indexeurs : recherche dans Prowlarr avec Gluetun arrêté | échec explicite |
| 8 | Détection continue : Suricata, catégorie P2P, sur `br0` | 0 alerte en régime normal ; alerte lors d'un test volontaire hors VPN (conteneur jetable) |
| 9 | Exposition : noms \*arr testés depuis un client externe en France | NXDOMAIN ou redirection Access |

## 10. Esquisse Compose de revue (non déployable)

```yaml
# apps/media-acquisition/compose.yml — ESQUISSE de revue, pas une configuration validée.
# Épingler versions et digests (Renovate) ; secrets uniquement dans le env_file runtime.
services:
  gluetun:
    image: ghcr.io/qdm12/gluetun:<version>@sha256:<digest>
    cap_add: [NET_ADMIN]
    devices: ["/dev/net/tun:/dev/net/tun"]
    env_file:
      # WIREGUARD_PRIVATE_KEY, HTTPPROXY_USER, HTTPPROXY_PASSWORD
      - /mnt/cpool/secrets/runtime/media-acquisition/gluetun.env
    environment:
      VPN_SERVICE_PROVIDER: protonvpn # décision D1
      VPN_TYPE: wireguard
      SERVER_COUNTRIES: <D1>
      PORT_FORWARD_ONLY: "on"
      VPN_PORT_FORWARDING: "on"
      # VPN_PORT_FORWARDING_UP_COMMAND / _DOWN_COMMAND : exemple qBittorrent du wiki Gluetun (§6.3)
      DNS_UPSTREAM_RESOLVER_TYPE: dot
      DNS_UPSTREAM_RESOLVERS: quad9
      DNS_UPSTREAM_IPV6: "off"
      BLOCK_MALICIOUS: "on"
      HTTPPROXY: "on"
      HTTPPROXY_STEALTH: "on"
      TZ: Europe/Paris
    sysctls:
      net.ipv6.conf.all.disable_ipv6: 1
    networks: [arr]
    # Aucun port hôte : WebUI via labels Traefik ; proxy :8888 joignable sur le réseau arr seulement.
    restart: unless-stopped

  qbittorrent:
    image: lscr.io/linuxserver/qbittorrent:<version>@sha256:<digest>
    network_mode: service:gluetun
    depends_on:
      gluetun:
        condition: service_healthy
        restart: true
    environment:
      PUID: "568"
      PGID: "568"
      UMASK: "002"
      TZ: Europe/Paris
      WEBUI_PORT: "8080"
    volumes:
      - /mnt/cpool/qbittorrent:/config
      - /mnt/cpool/media:/data
    restart: unless-stopped

networks:
  arr:
    name: arr
```

## 11. Risques résiduels et questions ouvertes

**Risques résiduels :**

- Le VPN protège la vie privée vis-à-vis du FAI et des pairs. Il ne change pas
  le statut juridique des contenus. En France, l'Arcom surveille les réseaux P2P
  publics : télécharger uniquement des contenus que l'on a le droit d'obtenir.
- La confiance est transférée au fournisseur VPN et à Quad9.
- Les requêtes de métadonnées (TMDB, TVDB, serveurs Servarr) et de sous-titres
  sortent par le WAN. Elles révèlent l'IP et l'intérêt pour certains titres à
  ces API. Accepté par défaut ; sinon, option N3.
- Certains trackers privés imposent leurs propres règles VPN ou IP : à vérifier
  tracker par tracker.
- Avec un proxy HTTP (méthode CONNECT), Prowlarr devrait laisser la résolution
  DNS au proxy. C'est attendu mais non prouvé : test P3.
- Le nom de l'interface VPN dans Gluetun et l'UID de l'image Seerr sont à
  confirmer sur les versions épinglées.

**Questions ouvertes pour l'opérateur :**

- pool cible et volumétrie (D3) ;
- bibliothèque existante à importer ;
- abonnement VPN déjà souscrit (D1) ;
- usage de Usenet (D4) ;
- utilisateurs distants (D5) ;
- modèle d'iGPU pour le transcodage.
