# Diagnostic Wi-Fi / DNS — workstation, 25 octobre 2026

## P0 — Constat et niveau de preuve

Le message « le Wi-Fi semble avoir des soucis » ne permet pas encore de conclure
à une défaillance radio. La workstation documentée utilise normalement
`eno1` en Ethernet ; son état **ne prouve pas** la qualité radio d'un
téléphone ou de la borne Wi-Fi. Les tests `just pfsense-console-test`
échouaient indépendamment du réseau parce qu'une assertion RFC5424 attendait
une seconde complète en vue `compact` après regroupement par minute.
La correction compare la minute en `compact` et conserve le timestamp
complet en `verbose`, avec expurgation dans les deux cas.

Faits des derniers relevés pfSense :
- Unbound PID 12710 démarré le 24/10 à 23:38:57, puis PID 2135 le
  25/10 à 00:04:56. Les journaux mentionnent une sortie du module DNSBL
  Python à 00:04:54, mais **pas de nouveau OOM à cette minute**.
- Unbound a rencontré un conflit de bind à 23:39:55 et des notices de
  redémarrage autour de 23:39 et 23:40. Cela étaye une piste de
  discontinuité DNS lors d'une reconfiguration/reload, sans démontrer
  quel service a déclenché l'action.
- Mémoire libre + inactive à 00:12 : environ 119,4 Mio. Les OOM noyau
  historiques autour de 02:10 et 22:03 restent distincts de ces
  redémarrages ; la causalité de Snort/pfBlockerNG est encore inconnue.
- Le DHCP LAN pfSense annonce `172.17.0.1`, alors que la workstation a
  déjà utilisé Quad9 au niveau `resolvectl`/NetworkManager. Un resolver
  public ne sait pas résoudre `sample.int.albandrieu.com` sans
  délégation privée. Un autre incident a établi une entrée Pi-hole
  incorrecte `sample.albandrieu.com -> 172.17.0.24`. Ces deux
  anomalies sont des **preuves historiques de chemins DNS concurrents**,
  et non des preuves que la borne Wi-Fi est en panne aujourd'hui.

## Séparer les quatre couches

| Observation reproductible | Cause à vérifier | Ne pas conclure |
| --- | --- | --- |
| Le client perd l'association au SSID | Borne, signal RSSI, roaming, alimentation, canal | Ce n'est pas une preuve contre Unbound |
| L'association reste active mais IP/route disparaît | DHCP, VLAN, passerelle, AP bridge | Ne pas changer DNSBL |
| TCP/443 externe par IP fonctionne, Quad9 DNS répond, pfSense DNS ne répond pas | Unbound, port 53 ou règle/ACL VLAN Wi-Fi | Ne pas supposer OOM |
| DNS pfSense fonctionne mais résolution système échoue | DNS actif local, DNS privé du téléphone, VPN/DoH/IPv6 | Ne pas attribuer à la borne |
| Tout fonctionne pendant un échantillon | Incident intermittent non capturé | Ce n'est pas une preuve de stabilité durable |

Le diagnostic local capture uniquement les noms d'interfaces, l'état Wi-Fi,
la fréquence et la puissance du signal si `iw` est disponible, les IPv4
de DNS actifs et DHCP, les résultats booléens des requêtes publiques via
pfSense/Quad9 et un TCP/443 vers 1.1.1.1. Les identifiants de réseaux
Wi-Fi, BSSID, profils NM complets, cookies, requêtes client privées et
journaux bruts ne sont jamais affichés. Il ne lance ni scan Wi-Fi,
ni reconfiguration, ni capture des paquets.

## Contrôles — workstation

1. Tester les contrats sans réseau :

```bash
just pfsense-wifi-path-test
```

2. Diagnostiquer le chemin de la workstation en lecture seule :

```bash
just pfsense-wifi-path
```

3. Capturer une perturbation intermittente (six échantillons espacés de
30 secondes, uniquement si nécessaire) :

```bash
python3 scripts/workstation/diagnose-wifi-path.py --check --samples 6 --interval 30
```

4. Sur un **client Linux connecté au Wi-Fi affecté**, exécuter la même
commande depuis le dépôt installé sur ce client. Sur un téléphone, contrôler
manuellement l'association, le DNS privé/DoH/VPN, l'adresse reçue, la
passerelle et la résolution de noms sans partager les identifiants.
Un résultat provenant d'`eno1` Ethernet doit toujours indiquer
`wifi_client_not_tested=true`.

5. En cas de dégradation DNS observée, vérifier pfSense en lecture seule :

```bash
bash scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh --check
```

6. Pour les noms privés et l'override Pi-hole existant :

```bash
just sample-dns-workstation
```

**Attention** : une réponse d'un résolveur public ne prouve pas qu'une règle
VLAN laisse toujours passer DNS/53. Un TCP/443 vers l'IP d'un serveur externe
peut être filtré ; son échec isolé est `INCONCLUSIVE` et ne prouve pas
une perte WAN. `NO_FAILURE_DURING_SAMPLE` n'est pas une certification
du Wi-Fi ni une validation du téléphone.

## Décision de récupération

**Aucun changement pfSense, Pi-hole, DNSBL, DHCP, Snort, CrowdSec ou AP
n'est autorisé sur ces seules preuves.** Si le DNS pfSense décroche,
corréler précisément le PID et l'heure de démarrage d'Unbound, les
événements `pfblocker_event=... timestamp=...`, les changements de
réseau/port 53, et les messages OOM. Si l'association Wi-Fi décroche
pendant que les services câblés restent joignables, collecter plutôt
les événements de la borne et le contexte RSSI/roaming.

### Préservation CI

La PR de correction reste en Draft, commits `[skip ci]`. Vérifier
`just pfsense-console-test`, `just pfsense-unbound-wifi-test` et
`just pfsense-wifi-path-test` dans un worktree SHA-épinglé avant
Ready/merge. Ne pas lancer volontairement de CI GitHub payante.
