# Workstation split-DNS — référence inter-dépôts et reprise rapide

> **Architecture canonique et runbook opérationnel :**
> [ansible-workstation/docs/homelab-split-dns-architecture.md](https://github.com/AlbanAndrieu/ansible-workstation/blob/master/docs/homelab-split-dns-architecture.md).
> **Répartition :** [ansible-workstation](https://github.com/AlbanAndrieu/ansible-workstation)
> (PR #15, fusionnée le 30/10) possède le profil `Wired eno1`, la NTA
> persistante et le dispatcher ; depuis le 10/11, il possède aussi les
> sondes et la réception (`mise run workstation-*`, scripts retirés de
> nabla-compose). nabla-compose garde le contrôle DefectDojo
> (`just defectdojo-workstation-dns-check`).
>
> **État retenu — 28/10 :** dispatcher **installé**,
> `nta_restored_by_event=PASS`, `diagnosis=PASS_REAPPLY_PERSISTENCE`
> sur un vrai événement NetworkManager `reapply`. Dernier contrôle
> read-only : `lan_profile=MATCH`, `dispatcher=ROOT_EXECUTABLE`,
> `link_nta=EXPECTED_ONLY`, `private_dns=PASS`,
> `public_dnssec=AUTHENTICATED`, `mode=READ_ONLY`.
> **Reste à recevoir : vérification après prochain reboot planifié**
> (section « Contrôle après reboot »).

Sources Ansible à lire d'abord :
[tâches split-DNS](https://github.com/AlbanAndrieu/ansible-workstation/blob/master/tasks/network_split_dns.yml),
[NTA dispatcher](https://github.com/AlbanAndrieu/ansible-workstation/blob/master/tasks/network_dnssec_nta_dispatcher.yml),
[configuration par défaut](https://github.com/AlbanAndrieu/ansible-workstation/blob/master/defaults/main.yml),
[unités hide-location](https://github.com/AlbanAndrieu/ansible-workstation/blob/master/tasks/services.yml),
[runbook de reprise Ansible](https://github.com/AlbanAndrieu/ansible-workstation/blob/master/docs/homelab-split-dns-recovery.md)
(commande d'application et rollback).

## Topologie et propriété

```text
workstation eno1 (172.17.0.57)
  NetworkManager profile "Wired eno1" [PERSISTANT]
    ipv4.dns=172.17.0.1
    ipv4.ignore-auto-dns=yes
    ipv4.dns-search=~int.albandrieu.com
  systemd-resolved [RUNTIME]
    NTA int.albandrieu.com sur eno1 (restaurée par le dispatcher)
    /etc/resolv.conf -> /run/systemd/resolve/stub-resolv.conf
      pfSense Unbound 172.17.0.1:53 (UDP/TCP)
        DNS privé -> 172.17.0.24 (Pi-hole/TrueNAS)
          defectdojo.int.albandrieu.com -> 172.17.0.24
            TrueNAS Traefik 443 -> DefectDojo
```

Le LAN split-DNS n'utilise ni pfSense DNS Forwarder (dnsmasq), ni DNS
public Cloudflare, ni HAProxy WAN. Ne jamais publier les noms `.int` à
l'extérieur. `resolvectl dns/domain` ne persiste rien dans NetworkManager.
Ne pas éditer `/etc/resolv.conf` ni les fragments historiques
`/etc/resolvconf/resolv.conf.d/head` et `base`.

**Règles de diagnostic :** ne pas remplacer `172.17.0.1` par un DNS public,
ne pas modifier `nsswitch.conf`, ne pas ajouter d'entrée `/etc/hosts`, ne
pas désactiver DNSSEC ou DNS-over-TLS globalement pour « tester ». Une
mesure isolée lente ou en timeout ne permet pas de déclarer pfSense DOWN.

## Recettes de diagnostic et réparation

Les sondes tournent **dans ansible-workstation** (`mise run`) ; seul le
contrôle DefectDojo reste dans nabla-compose (`just`) :

```bash
cd ~/w/ansible-workstation
mise run workstation-split-dns-check
mise run test-offline
cd ~/w/nabla-compose
just defectdojo-workstation-dns-check
```

`workstation-split-dns-check` (`scripts/homelab-split-dns.py --check`)
est en lecture seule : profil NetworkManager, domaine route-only
persistant, DNS effectif de systemd-resolved, getent/NSS, réponse directe
de pfSense en UDP **et** TCP, statut des unités hide-location. Aucune
valeur secrète. Sortie 0 uniquement si toutes les couches sont confirmées.

Réparation LOCALE et EXPLICITE (jamais en mode check) :

```bash
cd ~/w/ansible-workstation
mise run workstation-split-dns-repair
# équivalent :
python3 scripts/homelab-split-dns.py --apply --acknowledge I_APPROVE_WORKSTATION_SPLIT_DNS_REPAIR
```

Le mode apply :

- refuse un profil actif autre que `Wired eno1`, un DNS NetworkManager
  différent de `172.17.0.1`, ou une configuration DHCP DNS inattendue ;
- refuse si pfSense UDP/53 ne confirme pas l'adresse A privée attendue ;
- désactive service ET timer hide-location lorsqu'ils sont enabled ;
- ajoute seulement le domaine route-only absent (`+ipv4.dns-search`
  additif) et conserve les autres domaines ;
- exécute `nmcli device reapply eno1`, `flush-caches`, puis relance check ;
- ne redémarre ni NetworkManager, ni pfSense, ni TrueNAS et n'ajoute pas
  d'entrée `/etc/hosts`.

La configuration durable reste celle d'Ansible.

## Branche de diagnostic pfSense UDP/53

Si le script indique `pfsense_udp=NO_RESPONSE`, ne pas masquer l'incident
par un DNS public ou un fichier hosts. Depuis la **même workstation** :

```bash
dig +time=3 +tries=1 @172.17.0.1 defectdojo.int.albandrieu.com A +stats
dig +tcp +time=3 +tries=1 @172.17.0.1 defectdojo.int.albandrieu.com A +stats
time resolvectl query -4 defectdojo.int.albandrieu.com
```

- UDP KO / TCP OK : suspecter le chemin UDP/53 (transit ou listener).
- UDP KO / TCP KO : chemin direct DNS pfSense NON CONFIRMÉ ; lire Unbound,
  règles réseau, charge et journaux contemporains.
- UDP OK / NSS KO : examiner NetworkManager, resolved et nsswitch.
- DNS confirmé mais lent : collecter des séries horodatées.

## Lenteur NSS ou resolved

Comparer au même instant, en lecture seule (pas de nouveau `--apply` tant
que la configuration répond) :

```bash
cd ~/w/ansible-workstation
mise run workstation-split-dns-check
time resolvectl query -4 defectdojo.int.albandrieu.com
time getent ahostsv4 defectdojo.int.albandrieu.com
resolvectl status eno1
grep '^hosts:' /etc/nsswitch.conf
readlink -f /etc/resolv.conf
```

Direct pfSense rapide mais `resolvectl` lent → routage DNS du système ;
`resolvectl` rapide mais `getent` lent → NSS ; tout lent ensemble →
événements réseau/pfSense contemporains.

### Diagnostic différentiel NSS (lecture seule)

```bash
cd ~/w/ansible-workstation
mise run test-offline
mise run workstation-nss-path   # --samples 2 --timeout 3, intermittence
```

`scripts/diagnose-nss-resolution.py` sonde cinq chemins, chacun
avec un timeout, sans modifier de configuration :

1. `resolvectl query -4` : API native `systemd-resolved` ;
2. `dig @127.0.0.53` : stub UDP local (analyse détaillée : `RCODE_SERVFAIL`,
   `RCODE_NXDOMAIN`, `RCODE_REFUSED`, `NO_A_ANSWER`, `NO_DNS_RESPONSE`,
   `TIMEOUT`) ;
3. `getent -s hosts:dns ahostsv4` : module `nss-dns` forcé ;
4. `getent -s hosts:resolve ahostsv4` : `nss-resolve` forcé (peut être absent) ;
5. `getent ahostsv4` : chaîne glibc `hosts:` réelle.

Classifications : `NSS_DEFAULT_CHAIN_SLOW_OR_BROKEN`,
`RESOLVED_STUB_UDP_SLOW_OR_BROKEN`, `NSS_DNS_PATH_SLOW_OR_BROKEN`,
`RESOLVED_NATIVE_SLOW_OR_UNVERIFIED` ou `PASS`. Tous les signaux
individuels sont conservés ; `PASS` est interdit si le stub ou `nss-dns`
forcé est défaillant. Un `nss-resolve` absent ne suffit pas à déclarer une
panne. `getent -s` ne modifie pas `/etc/nsswitch.conf` : ne pas ajouter
`resolve` ni retirer `mdns4_minimal` de `hosts:` sans preuve de l'endroit où
naît le délai ; toute correction se prépare **dans ansible-workstation**,
réversible.

**Critère de clôture :** `mise run workstation-nss-path` répond rapidement via
la chaîne NSS par défaut, sur plusieurs essais et après redémarrage. Un
`WARN: NSS query slow despite success` reste un problème ouvert même si le
diagnostic DNS global est `PASS`.

Observations complémentaires :

```bash
resolvectl statistics
systemctl status systemd-resolved --no-pager
journalctl -u systemd-resolved --since '-15 min' --no-pager
```

`DNSOverTLS=opportunistic` peut ajouter une latence de négociation
([resolved.conf](https://www.freedesktop.org/software/systemd/man/resolved.conf.html)),
mais n'est pas une cause prouvée : ne pas le désactiver à l'aveugle.

## DNSSEC privé : diagnostic

```bash
cd ~/w/ansible-workstation
mise run test-offline
mise run workstation-dnssec-check
```

`scripts/diagnose-dnssec-chain.py` compare en deux cycles
bornés, sans `sudo`, mutation, reset de statistiques ni redémarrage :

- `resolvectl query -4 defectdojo.int.albandrieu.com` avec et sans
  `--validate=no` (ne désactive DNSSEC **que pour la requête**) ;
- `cloudflare.com` (public, signé) avec et sans `--validate=no` ;
- `dig @172.17.0.1 cloudflare.com A +dnssec` et `com DS +dnssec` (RRSIG) ;
- `dig @172.17.0.1 dnssec-failed.org A +dnssec` (`SERVFAIL` attendu).

Interprétation :

- pfSense `ANSWER` sans `RRSIG` avec `DO=1` : examiner Unbound (forwarder,
  filtrage, signatures transmises) ;
- `pfsense_dnssec_bogus=RCODE_SERVFAIL` : validation amont cohérente, sans
  garantir la transmission de chaque signature ;
- validé KO et `--validate=no` OK dans les deux cycles : validation locale
  **fortement suspecte** ;
- les deux modes KO : problème non isolé à DNSSEC ;
- tout PASS : intermittence non reproduite, surveiller sans modifier.

Références : [Ubuntu DNSSEC troubleshooting](https://ubuntu.com/server/docs/how-to/networking/dnssec-troubleshooting/),
[resolvectl](https://www.freedesktop.org/software/systemd/man/latest/resolvectl.html),
[Negative Trust Anchors](https://www.freedesktop.org/software/systemd/man/latest/dnssec-trust-anchors.d.html).

## NTA privée `int.albandrieu.com`

**Décision (27/10) :** une *Negative Trust Anchor* limitée à la zone privée
non signée `int.albandrieu.com`, plutôt que `DNSSEC=no` pour tous les noms.
Motif : validation normale en TIMEOUT sur DefectDojo privé alors que
`--validate=no` répondait, et pfSense transmettait bien `RRSIG`/`AD` pour
les zones publiques.

### NTA runtime (opt-in, réversible, non persistante)

```bash
cd ~/w/ansible-workstation
mise run test-offline
mise run workstation-dnssec-nta-check || true   # exit 1 possible tant que DNSSEC privé expire

# Action explicite : NTA uniquement sur eno1. Refuse si le profil n'est pas
# Wired eno1, DNS != 172.17.0.1, zone route-only absente ou autres NTA présentes.
mise run workstation-dnssec-nta-try

resolvectl query -4 defectdojo.int.albandrieu.com
getent ahostsv4 defectdojo.int.albandrieu.com
resolvectl query -4 cloudflare.com     # doit rester "Data is authenticated: yes"
mise run workstation-nss-path
just -f ~/w/nabla-compose/justfile defectdojo-workstation-dns-check
```

Rollback, seulement si la liste NTA du lien était vide au départ :

```bash
mise run workstation-dnssec-nta-rollback
```

Il n'efface la liste que si elle contient exactement `int.albandrieu.com` ;
aucun fichier édité, `DNSSEC=yes` et DoT inchangés, aucun redémarrage.

### Persistance par Ansible

- **Dispatcher par interface (retenu, installé le 28/10)** :
  `files/networkmanager-homelab-nta-dispatcher.sh` →
  `/etc/NetworkManager/dispatcher.d/90-nabla-private-dnssec-nta`, via
  `playbooks/homelab-dns.yml --tags dns`. Flags
  `workstation_split_dns_nta_dispatcher_enabled` /
  `..._remove_enabled` (désactivés par défaut). N'agit que pour
  `Wired eno1` / `eno1`, DNS `172.17.0.1` et `~int.albandrieu.com`, sur
  `up`, `dhcp4-change`, `reapply` ; ne touche pas aux NTA des autres
  interfaces/VPN.
- **Fichier `.negative` global (non retenu)** : `tasks/network_dnssec_nta.yml`
  créerait `/etc/dnssec-trust-anchors.d/90-nabla-int-albandrieu.negative`,
  limité à la zone mais **appliqué à tous les liens** du poste ; flags
  `workstation_split_dns_persistent_nta_enabled` /
  `..._remove_enabled` à laisser à `false` sans validation de l'impact VPN.

### Réception du dispatcher

```bash
cd ~/w/ansible-workstation
mise run test-offline
mise run workstation-dnssec-dispatcher-check
mise run workstation-dnssec-dispatcher-exercise
mise run workstation-dnssec-dispatcher-check
```

`scripts/accept-private-nta-dispatcher.py` : `-check` est
strictement en lecture seule. `-exercise` est une opération root
**explicite** : elle exige `eno1` dans `Wired eno1`, DNS uniquement
`172.17.0.1`, `~int.albandrieu.com`, exactement la NTA privée attendue et
un dispatcher `root:root` exécutable non accessible au groupe/autres. Elle
vide **temporairement** la NTA de `eno1`, appelle
`nmcli device reapply eno1` et attend la restauration ; sinon rollback
borné vers la seule NTA privée initiale. Un reapply peut perturber
brièvement le LAN : ne pas lancer durant un accès réseau critique.

Critères : `nta_restored_by_event=PASS`, `private_dns=PASS`,
`public_dnssec=AUTHENTICATED`, `diagnosis=PASS_REAPPLY_PERSISTENCE`.
Sinon, garder le chantier ouvert et lire les journaux de
`NetworkManager-dispatcher` plutôt que de désactiver DNSSEC.

### Contrôle après reboot

Après le **prochain reboot contrôlé** (ne pas redémarrer uniquement pour
cette preuve), **uniquement en lecture seule** :

```bash
cd ~/w/ansible-workstation
mise run workstation-dnssec-dispatcher-check
```

Attendu : `lan_profile=MATCH`, `dispatcher=ROOT_EXECUTABLE`,
`link_nta=EXPECTED_ONLY`, `private_dns=PASS`,
`public_dnssec=AUTHENTICATED`, sans ajout manuel de NTA. Ne pas relancer
`--exercise` pour cette étape.

## Validation DONE

Confirmer que hide-location est désactivé, que le profil NM persiste
`172.17.0.1` et `~int.albandrieu.com` après reapply puis reboot, que la NTA
privée est restaurée sans action manuelle, que getent et Chrome résolvent
les services privés, et que dig direct UDP **et** TCP n'expire pas. Si les
timeouts UDP restent, ouvrir un chantier pfSense/Unbound **séparé** de la
reprise Chrome.

## Historique et leçons

- **27/10, 21:21–21:34 CET** — journaux sudo : `hide-location.service`
  (relancé par son timer) exécutait
  `resolvectl dns eno1 9.9.9.9 149.112.112.112`. Service et timer
  désactivés ; `172.17.0.1` et `~int.albandrieu.com` rétablis.
- **27/10** — un `dig` UDP direct a expiré (3 s) alors que `resolvectl`
  répondait en 11,5 s ; non reproduit à 22:24 (TCP NOERROR 27 ms). Une
  expiration isolée n'est pas une panne pfSense.
- **27/10, 22:24** — `client_nss=UNRESOLVED (14 s)` avec DNS pfSense OK ;
  `workstation-split-dns-repair` → `diagnosis=PASS`. Latence NSS variable
  ensuite (2 s, 5,2 s, `getent` 25 s contre `resolvectl` 0,149 s).
- **27/10, 22:51** — la v1 du diagnostic NSS (`dig +short`) ne distinguait
  pas `SERVFAIL`/`NXDOMAIN`/absence de réponse : v2 avec RCODE et
  échantillons.
- **27/10, 23:01** — `resolvectl statistics` : 46 468 verdicts `Bogus`
  cumulés ; 1 141 `DNSSEC validation failed: no-signature` sur des domaines
  **publics** (github.com, google.com, …). Chantier distinct, non résolu par
  la NTA privée.
- **27/10, 23:XX** — DefectDojo privé : validé TIMEOUT / `--validate=no` OK,
  pfSense signe le public → NTA runtime : DefectDojo 33,4 ms, `cloudflare.com`
  authentifié 43,1 ms.
- **28/10** — gate Ansible : `Ran 0 tests`, `--list-tasks` vide et `--check`
  limité à `Gathering Facts` = **résultat invalide**, pas une convergence ;
  `import_role: name: ../` rendait la sélection de tâches impossible
  (remplacé par `import_tasks`). `changed=1` en `--check` n'est pas une
  installation. `direnv .envrc is blocked` est sans rapport.
- **28/10** — dispatcher installé (`ok=12 changed=1 failed=0`), exercice
  `reapply` PASS.
- **Ouvert** — `nss_default=A_CONFIRMED (4,8 s)` encore lent ; journaux
  `no-signature` publics ; preuve post-reboot.
