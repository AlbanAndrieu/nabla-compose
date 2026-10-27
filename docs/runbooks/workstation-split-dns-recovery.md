# Workstation split-DNS — référence inter-dépôts et reprise rapide

Mise à jour : 27 octobre 2026. **Source d'autorité de la persistance :**
[ansible-workstation](https://github.com/AlbanAndrieu/ansible-workstation),
[PR Ansible #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15) (Draft).
**nabla-compose possède les diagnostics et runbooks homelab**, pas le
provisionnement de la workstation. Les agents doivent d'abord lire :

- [Tâches de split-DNS](https://github.com/AlbanAndrieu/ansible-workstation/blob/fix/preserve-homelab-split-dns-20261027/tasks/network_split_dns.yml)
- [Configuration par défaut](https://github.com/AlbanAndrieu/ansible-workstation/blob/fix/preserve-homelab-split-dns-20261027/defaults/main.yml)
- [Gestion des unités hide-location](https://github.com/AlbanAndrieu/ansible-workstation/blob/fix/preserve-homelab-split-dns-20261027/tasks/services.yml)
- [Runbook de reprise Ansible](https://github.com/AlbanAndrieu/ansible-workstation/blob/fix/preserve-homelab-split-dns-20261027/docs/homelab-split-dns-recovery.md)

## Topologie et propriété

    workstation eno1 (172.17.0.57)
      NetworkManager profile "Wired eno1" [PERSISTANT]
        ipv4.dns=172.17.0.1
        ipv4.ignore-auto-dns=yes
        ipv4.dns-search=~int.albandrieu.com
      systemd-resolved [RUNTIME]
        /etc/resolv.conf -> /run/systemd/resolve/stub-resolv.conf
          pfSense Unbound 172.17.0.1:53 (UDP/TCP)
            DNS privé -> 172.17.0.24 (Pi-hole/TrueNAS)
              defectdojo.int.albandrieu.com -> 172.17.0.24
                TrueNAS Traefik 443 -> DefectDojo

Le LAN split-DNS n'utilise ni pfSense DNS Forwarder (dnsmasq),
ni DNS public Cloudflare, ni HAProxy WAN. Ne jamais publier les
noms .int à l'extérieur. Les commandes resolvectl dns/domain
ne persistent pas les valeurs dans NetworkManager.
Ne pas éditer /etc/resolv.conf ni les fragments historiques
/etc/resolvconf/resolv.conf.d/head et base.

## Incidents réellement observés

Le 27/10, des journaux sudo ont **prouvé** que
hide-location.service, relancé périodiquement par son timer,
exécutait resolvectl dns eno1 9.9.9.9 149.112.112.112 entre
21:21 et 21:34 CET. L'opérateur a désactivé les deux unités :
is-enabled=disabled/disabled, 0 timers. Il a rétabli 172.17.0.1
et ~int.albandrieu.com, confirmé la résolution NSS et l'interface
DefectDojo **opérationnelle dans Chrome**. La suite Ansible 7/7
PASS a été exécutée sur la workstation.

Un reapply NetworkManager a ensuite réussi ; resolvectl et getent
retournaient l'adresse privée correcte. L'exécution de la recette
Just depuis le worktree ansible-workstation a produit
« error: no justfile found » : **mauvais répertoire de travail**,
pas un échec DNS.

**Incident restant, distinct du drift Quad9 :** une requête directe
dig UDP vers 172.17.0.1:53 a expiré après trois secondes, tandis
que resolvectl query -4 a répondu en 11,5065 s. La réponse du
résolveur système n'atteste pas le fonctionnement de UDP/53
direct sur cet essai. Une seule expiration ne démontre pas une
panne pfSense globale. Comparer DNS UDP/TCP et capture temporelle
avant d'incriminer Unbound, le filtrage ou une surcharge.

## Recettes de diagnostic et réparation

Toujours commencer **dans nabla-compose** :

    cd ~/w/nabla-compose
    just workstation-split-dns-check
    just workstation-split-dns-test
    just defectdojo-workstation-dns-check

Le premier utilise scripts/workstation/homelab-split-dns.py --check,
en lecture seule : il compare profil NetworkManager, domaine route-only
persistant, DNS effectif de systemd-resolved, getent/NSS,
réponse directe de pfSense en UDP **et** TCP, statut des
unités hide-location. Les sorties résument les états des couches et
ne divulguent aucun secret. Sortie 0 uniquement si toutes les
couches sont confirmées ; sortie 1 sinon.

Réparation LOCALE et EXPLICITE (jamais en mode check) :

    cd ~/w/nabla-compose
    just workstation-split-dns-repair

Équivalent sans Just :

    python3 scripts/workstation/homelab-split-dns.py --apply --acknowledge I_APPROVE_WORKSTATION_SPLIT_DNS_REPAIR

Le mode apply :
- refuse un profil actif autre que Wired eno1, un DNS NetworkManager
  différent de 172.17.0.1, ou une configuration DHCP DNS inattendue ;
- refuse si pfSense UDP/53 ne confirme pas l'adresse A privée attendue ;
- désactive service ET timer hide-location lorsqu'ils sont enabled ;
- ajoute seulement le domaine route-only absent, avec le modificateur
  additif +ipv4.dns-search ; conserve tous les autres domaines ;
- exécute nmcli device reapply eno1 puis flush-caches et relance check ;
- ne redémarre ni NetworkManager, ni pfSense, ni TrueNAS et
  n'ajoute pas d'entrée /etc/hosts.

Avant un reboot ou un changement de réseau, contrôler le profil
et le DNS effectif. La configuration durable est celle d'Ansible PR #15,
son activation et sa fusion restent séparées de ce runbook.

## Branche de diagnostic pfSense UDP/53

Si le script indique pfsense_udp=NO_RESPONSE, ne pas masquer
l'incident par un DNS public ou une correction de fichier hosts.
Exécuter depuis la **même workstation** :

    dig +time=3 +tries=1 @172.17.0.1 defectdojo.int.albandrieu.com A +stats
    dig +tcp +time=3 +tries=1 @172.17.0.1 defectdojo.int.albandrieu.com A +stats
    time resolvectl query -4 defectdojo.int.albandrieu.com

- UDP KO / TCP OK : suspecter le chemin UDP/53 (transit ou listener).
- UDP KO / TCP KO : chemin direct DNS pfSense NON CONFIRMÉ ; lire Unbound,
  règles réseau, charge et journaux contemporains.
- UDP OK / NSS KO : examiner NetworkManager, resolved et nsswitch.
- DNS confirmé mais requêtes lentes : collecter des séries horodatées ;
  ne pas déclarer pfSense DOWN sur une mesure isolée.

## Validation DONE

Confirmer que hide-location est désactivé, que le profil NM
persiste 172.17.0.1 et ~int.albandrieu.com après reapply puis
reboot, que getent et Chrome résolvent les services privés, et que
dig direct UDP **et** TCP n'expire pas. Si les timeouts UDP restent,
ouvrir un chantier pfSense/Unbound **séparé** de la reprise Chrome.
