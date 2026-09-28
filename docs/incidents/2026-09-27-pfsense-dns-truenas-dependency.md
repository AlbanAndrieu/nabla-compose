# Incident DNS LAN après reboot TrueNAS — 2026-09-27

## Résumé

Après la mise à niveau de pfSense vers 26.07-RELEASE et un reboot TrueNAS, plusieurs clients LAN, dont un Samsung Galaxy S24 Ultra, se sont retrouvés dans un état Android « connecté sans Internet ».

Le diagnostic a montré que le problème principal n'était pas une panne générale du WAN IPv4 :

- pfSense joignait Internet par IPv4 ;
- le routage par défaut WAN était correct ;
- Unbound sur pfSense résolvait correctement les noms ;
- le monitoring WANGW via `dpinger` fonctionnait après réactivation ;
- le Samsung pouvait établir certains flux HTTPS/QUIC Internet.

Le défaut certain identifié côté LAN était que Kea distribuait encore `172.17.0.24` (TrueNAS) comme serveur DNS alors que, après reboot, aucun service DNS n'écoutait sur `172.17.0.24:53`.

## Symptômes observés

- Samsung S24 Ultra : IP `172.17.0.14`, gateway `172.17.0.1`.
- Android : « connecté sans Internet ».
- Play Store : erreur réseau.
- TrueNAS `172.17.0.24` joignable en ICMP, mais DNS indisponible :

```text
dig @172.17.0.24 google.com
;; no servers could be reached

nc -vz -w2 172.17.0.24 53
connection refused
```

- Kea généré par pfSense :

```json
{
  "name": "domain-name-servers",
  "data": "172.17.0.24"
}
```

- Gateway DHCP correcte :

```json
{
  "name": "routers",
  "data": "172.17.0.1"
}
```

## Cause racine

La configuration DHCP LAN dépendait d'un resolver DNS hébergé sur TrueNAS.

Cette dépendance est fragile car TrueNAS est lui-même une plateforme d'hébergement de services et peut redémarrer avec ses applications encore arrêtées ou en cours de récupération. Quand le resolver hébergé sur TrueNAS n'est pas encore disponible, les clients LAN obtiennent néanmoins son IP comme DNS primaire et peuvent perdre la résolution ou entrer dans des mécanismes de fallback variables selon les OS/applications.

Cela crée une dépendance cyclique potentielle :

```text
Clients / Talos / Kubernetes
        |
        v
DNS sur TrueNAS
        |
        v
TrueNAS Apps / services
        |
        v
dépendances réseau/DNS au démarrage
```

Pour Talos/Kubernetes, ce type de chaîne est particulièrement risqué : les composants de bootstrap et CoreDNS ne doivent pas dépendre d'un resolver dont la disponibilité dépend elle-même du bon démarrage de la plateforme hébergeant le cluster ou ses services auxiliaires.

## Correction appliquée

Dans pfSense :

```text
Services -> DHCP Server -> LAN
DNS server: 172.17.0.24 -> 172.17.0.1
```

Le resolver LAN général devient donc pfSense/Unbound.

TrueNAS peut continuer à héberger un resolver spécialisé (Pi-hole/AdGuard/private-zone) mais ne doit pas être le SPOF DNS global du LAN.

## Contrat d'architecture cible

```text
LAN clients
   |
   v
pfSense / Unbound
172.17.0.1
   |
   +--> Internet recursive DNS
   |
   +--> conditional/private-zone delegation
           |
           +--> TrueNAS resolver(s), when available
```

### Règles

1. Le DHCP LAN distribue pfSense/Unbound (`172.17.0.1`) comme resolver général.
2. Les zones privées peuvent être déléguées conditionnellement vers un resolver TrueNAS.
3. Une panne/reboot TrueNAS ne doit pas supprimer la résolution DNS générale du LAN.
4. Talos/Kubernetes bootstrap, control plane et CoreDNS ne doivent pas dépendre d'un resolver dont la disponibilité dépend de TrueNAS Apps.
5. Les probes d'observabilité doivent distinguer :
   - disponibilité du resolver général pfSense ;
   - disponibilité des zones privées déléguées ;
   - disponibilité d'un resolver optionnel TrueNAS.

## Actions de prévention

- [x] Remplacer le DNS DHCP LAN `172.17.0.24` par `172.17.0.1`.
- [ ] Vérifier le renouvellement DHCP des clients critiques après changement.
- [ ] Documenter explicitement les zones privées qui restent déléguées à TrueNAS.
- [ ] Exécuter le smoke DNS post-reboot (les garde-fous statiques/runtime sont maintenant versionnés) :
  - `dig @172.17.0.1 example.com`
  - `dig @172.17.0.1 <nom-zone-privee>`
  - test direct du resolver TrueNAS, sans en faire un prérequis global.
- [x] Ajouter au runbook Talos un contrôle de dépendance DNS/cycle avant bootstrap et après reboot, et faire générer `machine.network.nameservers: [172.17.0.1]` par défaut.
- [ ] Ajouter une alerte dédiée lorsque le resolver TrueNAS tombe, sans classifier le LAN entier comme « Internet down » tant que pfSense/Unbound reste sain.
- [ ] Revalider IPv6 séparément : le WAN n'avait pas de route IPv6 par défaut au moment de l'incident et les RA LAN ont été désactivés temporairement pour isoler le diagnostic.

## Procédure post-upgrade pfSense 26.07

L'upgrade vers pfSense 26.07 a nécessité une remise en état explicite de plusieurs
packages tiers. Ne pas considérer l'upgrade terminé tant que ces composants n'ont
pas été réinstallés et validés.

### CrowdSec

Réinstaller CrowdSec avec le script officiel du package pfSense :

```sh
fetch https://raw.githubusercontent.com/crowdsecurity/pfSense-pkg-crowdsec/refs/heads/main/install-crowdsec.sh
sh install-crowdsec.sh
```

Validation minimale :

```sh
pkg info | grep -i crowdsec
pgrep -laf 'crowdsec|crowdsec-firewall-bouncer'
```

### pfSense REST API

Réinstaller le package RESTAPI compatible pfSense 26.07 :

```sh
pkg-static -C /dev/null add https://github.com/pfrest/pfSense-pkg-RESTAPI/releases/download/v2.10.2/pfSense-26.07-pkg-RESTAPI.pkg
```

Validation minimale :

```sh
pkg info | grep -i restapi
```

Puis valider l'endpoint REST API canonique déjà utilisé par l'observabilité :

```text
https://home.albandrieu.com:10443/api/v2/system/version
```

### Zabbix Agent 7

Après l'upgrade, les packages étaient encore installés :

```text
pfSense-pkg-zabbix-agent7-1.1_1
zabbix7-agent-7.0.27
```

mais aucun daemon Zabbix ne tournait et aucun listener n'était présent. Le fichier
runtime `/usr/local/etc/zabbix7/zabbix_agentd.conf` avait également disparu
alors que le package fournissait encore `zabbix_agentd.conf.sample`.

Réinstaller `pfSense-pkg-zabbix-agent7` depuis l'UI :

```text
System
  -> Package Manager
    -> Installed Packages
      -> pfSense-pkg-zabbix-agent7
        -> Reinstall
```

La réinstallation pfSense régénère la configuration et le wrapper de service
`/usr/local/etc/rc.d/zabbix_agentd.sh`. Ne pas recréer manuellement
`zabbix_agentd.conf` depuis le fichier sample tant que le package pfSense peut
le régénérer.

Configuration temporaire validée pendant la remise en état :

```text
Server=172.17.0.24
ServerActive=172.17.0.24
Hostname=pfsense
ListenIP=172.17.0.1
ListenPort=10050
```

Le serveur Zabbix Docker sur TrueNAS reste volontairement arrêté pour le moment.
Les erreurs d'active checks vers `172.17.0.24:10051` sont donc attendues et ne
signifient pas que l'agent pfSense est down.

Validation finale observée le 2026-09-27 :

```text
zabbix_agentd is running as pid 17682.
TCP 172.17.0.1:10050 LISTEN
collector + 3 listeners + active checks workers démarrés
```

Commandes de validation :

```sh
service zabbix_agentd status
pgrep -laf zabbix
sockstat -4 -6 -l | grep 10050
grep -E '^(Server|ServerActive|Hostname|ListenIP|ListenPort)=' \
  /usr/local/etc/zabbix7/zabbix_agentd.conf
tail -50 /var/log/zabbix-agent/zabbix_agentd.log
```

Puis, quand le serveur Zabbix Docker sera redémarré sur TrueNAS, valider
`172.17.0.24:10051` et la reprise des active checks.

### Checklist de sortie post-upgrade

```text
Unbound / DNS        OK
Kea DHCP             OK
DNS DHCP LAN         172.17.0.1
WANGW / dpinger      Online
CrowdSec             running
pfSense REST API     reachable
Zabbix agent         running / TCP 10050
```

## Notes complémentaires

Le même incident a aussi montré :

- `dpinger` était initialement arrêté parce que le monitoring WANGW était explicitement désactivé, pas parce que le daemon était cassé ;
- après réactivation, WANGW est revenu `Online` ;
- l'exposition publique du WebConfigurator pfSense reçoit des tentatives d'authentification automatisées et doit être traitée séparément comme dette de sécurité.
