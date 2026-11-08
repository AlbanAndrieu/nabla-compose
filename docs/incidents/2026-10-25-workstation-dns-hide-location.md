# Workstation : `hide-location.service` réécrit le DNS de `eno1` vers Quad9

Date : 2026-10-25 → 2026-10-27. Preuves : diagnostic
`just pfsense-wifi-path`, `journalctl`/sudo sur la workstation.
Procédure courante :
[workstation-split-dns-recovery.md](../runbooks/workstation-split-dns-recovery.md).

## Symptômes

- « Le Wi-Fi a des soucis » ; les noms privés
  (`sample.int.albandrieu.com`) ne se résolvent plus depuis la
  workstation, DefectDojo inaccessible dans Chrome.
- pfSense et Pi-hole répondent correctement en direct
  (`dig @172.17.0.1` et `dig @172.17.0.24` → `172.17.0.24`), mais
  `getent ahostsv4` ne renvoie rien : la panne est **côté client**.

| Source | DNS |
| --- | --- |
| DHCP LAN (Kea) | `172.17.0.1` |
| Profil NetworkManager `Wired eno1` | `172.17.0.1`, `ignore-auto-dns=yes` |
| `resolvectl dns eno1` (actif) | `9.9.9.9`, `149.112.112.112` |

## Cause racine

Le rôle `ansible-workstation` installe `/opt/script/hide-location.sh`,
`hide-location.service` et `hide-location.timer` (toutes les minutes,
conditionnés par `macchanger_enabled`). Le script appelle
`resolvectl dns <interface> 9.9.9.9 149.112.112.112` dès qu'il voit le
DNS LAN. Le 27/10, sudo et `journalctl` ont prouvé ces appels répétés sur
`eno1`. Un résolveur public ne connaît pas la zone privée.

## Correctif

Le 27/10, l'opérateur a désactivé le service **et** le timer ; DefectDojo
est de nouveau accessible. La remédiation durable (changement DNS explicite
et réversible, noms privés protégés par split-DNS) relève de
[ansible-workstation PR #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15).

## Leçons

- Comparer trois étages : profil NetworkManager, `nmcli -g IP4.DNS device
  show eno1` et `resolvectl dns eno1`. `runtime_dns_drift` localise un
  écart de valeurs, pas son auteur.
- Le source Ansible versionné visait `wlp0s20f3` : seule la preuve
  d'exécution (journal) a permis de l'accuser pour `eno1`. Ne rien
  désactiver à l'aveugle.
- Un test sur `eno1` (Ethernet) ne dit rien de la radio Wi-Fi d'un
  téléphone ou de la borne.

## Suites

- Un second défaut reste distinct et ouvert : `dig` UDP vers
  `172.17.0.1:53` a expiré alors que `resolvectl query` répondait en
  11,5 s. Suivi dans le runbook de split-DNS.
