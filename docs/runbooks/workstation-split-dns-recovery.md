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

## Réception opérateur — 27 octobre, 22:24 CET

Une nouvelle exécution **sur la workstation**, depuis
`cd ~/w/nabla-compose`, confirme les points suivants :

- `just workstation-split-dns-test` : **16/16 PASS**
  (deux exécutions successives, sans pytest).
- Avant application : profil NM `MATCH`, route
  `PERSISTED`, résolveur `MATCH`, domaine `ROUTED`,
  pfSense UDP et TCP `A_CONFIRMED (0.0s)`, mais
  **`client_nss=UNRESOLVED (14.0s)`**. La classification
  `CLIENT_PRIVATE_SPLIT_DNS_PATH` / exit 1 est correcte.
- L'opérateur a exécuté explicitement
  `just workstation-split-dns-repair`. L'outil a réappliqué
  le profil local, vidé le cache et contrôlé le résultat :
  **`client_nss=A_CONFIRMED (2.0s)`, `diagnosis=PASS`**.
- Le `just workstation-split-dns-check` suivant : **PASS**,
  `client_nss=A_CONFIRMED (5.2s)` et avertissement
  **`WARN: NSS query slow despite success`**.
- Les unités `hide-location.timer` et `hide-location.service`
  restent `disabled`. Le profil `~int.albandrieu.com`
  est maintenant `PERSISTED`.
- Contrôle direct pfSense `dig +tcp @172.17.0.1
  defectdojo.int.albandrieu.com A` à **22:24:07 CET** :
  **NOERROR**, réponse A `172.17.0.24`, **27 ms**.
  Les vérifications internes de l'outil classent aussi UDP
  et TCP `A_CONFIRMED` lors de ces exécutions.

**Bilan :** la réparation locale est acceptée **au runtime** ;
la configuration est écrite dans NetworkManager et non
`resolvconf`. Le précédent timeout UDP isolé n'est pas
reproduit durant ce contrôle ; ne pas le classer « résolu
définitivement » ni « pfSense DOWN ». Le **délai NSS
variable** (14 s KO, 2 s OK, 5,2 s OK) reste un sujet de
performance/intermittence : décomposer avec des mesures
contemporaines, mais ne pas inverser les statuts DNS qui
ont effectivement répondu.

### Diagnostic read-only si la lenteur NSS réapparaît

Depuis la workstation, sans nouveau `--apply` tant que
la configuration continue de répondre :

```bash
cd ~/w/nabla-compose
just workstation-split-dns-check

# Comparer directement au même instant les couches DNS et NSS :
dig +time=3 +tries=1 @172.17.0.1 \
  defectdojo.int.albandrieu.com A +stats
dig +tcp +time=3 +tries=1 @172.17.0.1 \
  defectdojo.int.albandrieu.com A +stats
time resolvectl query -4 defectdojo.int.albandrieu.com
time getent ahostsv4 defectdojo.int.albandrieu.com

# Inspecter les DNS et domaines effectivement associés au lien.
resolvectl status eno1
grep '^hosts:' /etc/nsswitch.conf
readlink -f /etc/resolv.conf
```

**Interprétation :** direct pfSense rapide, mais
`resolvectl` lent → examiner le routage DNS du système et
les requêtes répétées. `resolvectl` rapide mais
`getent` lent → examiner NSS. Si les trois chemins
ralentissent ou expirent ensemble, rechercher des évènements
réseau/pfSense du même instant.

**Acceptation persistante finale encore non prouvée :**
vérifier après un redémarrage contrôlé de la workstation
que NetworkManager applique `172.17.0.1` et
`~int.albandrieu.com`, que `hide-location` reste
désactivé et que `getent`/Chrome restent opérationnels.

## Régression NSS isolée — 27 octobre, après 22:24 CET

L'opérateur a refait le contrôle sur la workstation :

- `just workstation-split-dns-check` :
  `nm_profile=MATCH`, `private_route=PERSISTED`,
  `resolved_link=MATCH`, `resolved_domain=ROUTED`,
  DNS pfSense UDP/TCP `A_CONFIRMED (0.0s)`.
  Mais `client_nss=A_CONFIRMED (12.4s)` : **DNS correct,
  NSS très lent** malgré `diagnosis=PASS`.
- `time resolvectl query -4 defectdojo.int.albandrieu.com` :
  **0,149 s**, réponse A `172.17.0.24` sur `eno1`.
- `time getent ahostsv4 defectdojo.int.albandrieu.com` :
  **25,030 s**, **aucune réponse imprimée**.
- `resolvectl status eno1` : DNS `172.17.0.1`,
  domaine `~int.albandrieu.com`, `DNSOverTLS=opportunistic`,
  `DNSSEC=yes/supported`, `DefaultRoute=yes`.
- Ligne `hosts:` antérieurement relevée :
  `files mdns4_minimal [NOTFOUND=return] dns mymachines`.
- `/etc/resolv.conf` est un lien vers le stub généré
  `/run/systemd/resolve/stub-resolv.conf`.

**Interprétation :** la résolution directe et la couche
`systemd-resolved` native répondent vite à cet instant,
tandis que le chemin `getent`/glibc NSS peut atteindre
25 s sans réponse. Il est **incorrect** d'attribuer cette
mesure à pfSense ou de considérer l'ensemble des fonctions
DNS défaillantes. Aucun changement de DNS n'est justifié
tant que le split-DNS de NetworkManager est intact.

### Diagnostic différentiel en une commande (lecture seule)

```bash
cd ~/w/nabla-compose
just workstation-nss-path-test
just workstation-nss-path
```

Source : `scripts/workstation/diagnose-nss-resolution.py`.
Cinq chemins distincts, chacun avec un timeout individuel,
sans modifier de fichier de configuration :

1. `resolvectl query -4` : API native `systemd-resolved`.
2. `dig @127.0.0.53` : stub DNS UDP local.
3. `getent -s hosts:dns ahostsv4` : forcer le module
   NSS `nss-dns`, sans les autres modules de `hosts:`.
4. `getent -s hosts:resolve ahostsv4` : forcer
   `nss-resolve` (optionnel et potentiellement absent).
5. `getent ahostsv4` : chaîne glibc `hosts:` réelle.

La commande classe entre
`NSS_DEFAULT_CHAIN_SLOW_OR_BROKEN`,
`RESOLVED_STUB_UDP_SLOW_OR_BROKEN`,
`NSS_DNS_PATH_SLOW_OR_BROKEN`,
`RESOLVED_NATIVE_SLOW_OR_UNVERIFIED`, ou `PASS`.
Un module `nss-resolve` absent **ne suffit pas** pour
déclarer une panne. La classification se fonde
d'abord sur le chemin NSS par défaut et la comparaison
avec le résolveur natif.

**Attention :** `getent -s` impose un module NSS
uniquement pour cette commande. Il ne modifie pas
`/etc/nsswitch.conf`. Ne pas ajouter `resolve`
ni retirer `mdns4_minimal` de `hosts:` tant
que les résultats des modules forcés ne démontrent
pas où le délai apparaît. Si `nss-resolve` est
disponible et plus rapide, préparer une correction
déclarative et réversible **dans ansible-workstation**,
avec sauvegarde des valeurs d'origine.

**Critère de clôture :** `just workstation-nss-path`
répond rapidement via la chaîne NSS par défaut,
sur plusieurs essais séparés et après redémarrage.
Même quand le diagnostic global DNS affiche `PASS`,
un avertissement `NSS query slow` reste un problème
de performance non résolu.

## Incident simultané resolved/stub/NSS — 27 octobre, 22:51 CET

Nouvelle exécution opérateur des recettes NSS :

- `just workstation-nss-path-test` : **11/11 PASS**, version
  initiale du contrat différentiel `v1` ; les tests ajoutés
  depuis restent **à exécuter**.
- `resolved_native=TIMEOUT (6.0s)` : la voie native
  `systemd-resolved` ne répond pas dans le délai imparti.
- `stub_udp=NO_ANSWER (2.0s)` : **v1** utilisait
  `dig +short` et ne distinguait pas `SERVFAIL`,
  `NXDOMAIN`, `NOERROR` sans A et absence de réponse DNS.
- `nss_dns=A_CONFIRMED (3.4s)` : la résolution glibc
  `nss-dns` forcée réussit, mais lentement.
- `nss_resolve=NO_ANSWER (0.0s)` : le module forcé
  n'a pas répondu ; son installation/disponibilité n'est
  **pas confirmée**.
- `nss_default=TIMEOUT (6.0s)` : la chaîne `hosts:`
  normale échoue également.

**Conclusion :** la précédente hypothèse « défaut NSS seul »
est insuffisante : `systemd-resolved` natif a aussi expiré
sur ce relevé. Il est possible que plusieurs couches soient
affectées ou que leur état change entre les probes
séquentielles. Aucun résultat ne justifie de modifier
`nsswitch.conf`, la configuration DNSSEC, DNS-over-TLS,
ou pfSense à l'aveugle.

### Correctif de diagnostic, sans mutation

`scripts/workstation/diagnose-nss-resolution.py` **v2** :

- analyse la réponse détaillée du stub DNS avec
  `dig +nocmd +noall +comments +answer` afin de
  distinguer `RCODE_SERVFAIL`, `RCODE_NXDOMAIN`,
  `RCODE_REFUSED`, `NO_A_ANSWER`,
  `NO_DNS_RESPONSE` et `TIMEOUT` ;
- conserve **tous les signaux individuels** même lorsque
  la panne native resolved est la première classification ;
- propose `--samples 2 --timeout 3`, sondes séquentielles
  avec délais bornés, pour repérer un symptôme intermittent ;
- interdit `PASS` si le stub ou `nss-dns` forcé est
  défaillant malgré une réponse positive de `getent` par défaut ;
- ne modifie aucun service ni aucune configuration.

```bash
cd ~/w/nabla-compose
git pull --ff-only
just workstation-nss-path-test
just workstation-nss-path-samples

# Observations complémentaires en lecture seule :
resolvectl status eno1
resolvectl statistics
systemctl status systemd-resolved --no-pager
journalctl -u systemd-resolved --since '-15 min' --no-pager
```

**Piste à vérifier, pas une attribution :** le relevé
`resolvectl status eno1` affichait
`DNSOverTLS=opportunistic` et `DNSSEC=yes/supported`.
Selon [la documentation systemd](https://www.freedesktop.org/software/systemd/man/resolved.conf.html),
le mode opportuniste tente le transport DNS-over-TLS et
revient à une autre voie si le serveur ne le supporte pas.
Ce mécanisme peut générer une latence de négociation,
mais aucun journal ne confirme que c'est la cause ici.
**Ne pas désactiver DNSSEC ou DoT pour tester à l'aveugle.**
Attendre les codes de réponse du stub et les événements
contemporains de `systemd-resolved`.

## P0 — Validation DNSSEC de la workstation, preuve du 27/10 à 23:01 CET

**Preuve fournie par l'opérateur :** `resolvectl status eno1`
continue d'indiquer `DNS 172.17.0.1`,
`~int.albandrieu.com`, `DNSSEC=yes/supported` et
`DNSOverTLS=opportunistic`. Le service
`systemd-resolved` est en cours d'exécution depuis
le 24/10 (pas un crash soudain). `resolvectl statistics`
affiche **716 115 transactions**, **5 077 timeouts**,
**803 failure responses** et **46 468 verdicts DNSSEC
`Bogus`**, compteurs **cumulatifs** depuis le
démarrage du service.

Le journal `systemd-resolved` fourni contient
**1 141 événements `DNSSEC validation failed: no-signature`**
sur la période visible (notamment 22:47–23:01 CET) :
`github.com`, `google.com`, `chatgpt.com`,
`telegram.org`, `dropbox.com`, ainsi que
des recherches `com IN DS` et `org IN DS`.
C'est une **preuve d'échec actif de la validation DNSSEC
sur de nombreux domaines publics**, pas seulement
`defectdojo.int.albandrieu.com`.
C'est compatible avec les `TIMEOUT` intermittents
de `resolved_native` et `getent`, sans prouver
quel maillon élimine les signatures ou provoque
la latence. Unbound/pfSense et les éventuels
intermédiaires ne sont pas reconnus responsables
à ce stade.

**Règle de diagnostic :** ne pas remplacer
`172.17.0.1` par un DNS public, ne pas éditer
`/etc/resolv.conf`, ne pas modifier `nsswitch.conf`
et ne pas désactiver DNSSEC/DNS-over-TLS globalement
sans vérifier les signatures DNSSEC côté pfSense.

### Test différentiel DNSSEC en lecture seule

Le script `scripts/workstation/diagnose-dnssec-chain.py`
compare dans deux cycles bornés :

- `resolvectl query -4 defectdojo.int.albandrieu.com`
  avec et sans `--validate=no` ;
- la résolution `cloudflare.com` (domaine public
  DNSSEC-signé) avec et sans `--validate=no` ;
- `dig @172.17.0.1 cloudflare.com A +dnssec`
  et `dig @172.17.0.1 com DS +dnssec` pour vérifier
  les réponses `RRSIG` ;
- `dig @172.17.0.1 dnssec-failed.org A +dnssec`
  pour observer `SERVFAIL` sur une zone volontairement
  invalide (indice de validation amont, pas preuve
  suffisante à lui seul).

`--validate=no` ne désactive DNSSEC **que sur la
requête contrôlée** ; ce n'est pas une reconfiguration
du lien ni du service `systemd-resolved`.
Un contraste répété « validated KO / bypass OK »
désigne le chemin de validation locale comme
**suspect**, mais ne détermine pas à lui seul
pourquoi les signatures sont absentes.

```bash
cd ~/w/nabla-compose
git pull --ff-only
just workstation-dnssec-test
just workstation-dnssec-check
```

Les **13 tests offline** ont été ajoutés mais sont
**à exécuter sur la workstation** ; ne pas
les présenter comme PASS avant réception.
`workstation-dnssec-check` n'exécute ni
`sudo`, ni mutation, ni reset de statistiques,
ni redémarrage de `systemd-resolved`.

**Interprétation après réception :**

- Upstream pfSense `ANSWER` sans `RRSIG` alors
  que l'en-tête demande DNSSEC (`DO=1`) :
  examiner la configuration Unbound (forwarder,
  filtrage des réponses, signatures transmises).
- `pfsense_dnssec_bogus=RCODE_SERVFAIL` :
  cohérent avec une validation en amont, mais ne
  garantit pas que chaque réponse DNSSEC soit
  correctement transmise au poste.
- `resolved` validé KO et `--validate=no` OK
  dans les deux cycles : validation locale
  **fortement suspecte**.
- Les deux modes KO : problème non isolé à DNSSEC ;
  rechercher les timeouts/transactions et journaux
  contemporains.
- Tous les contrôles PASS : incident intermittent
  non reproduit à cet instant, continuer la
  surveillance sans modifier la configuration.

**Source technique :**
[Ubuntu DNSSEC troubleshooting](https://ubuntu.com/server/docs/how-to/networking/dnssec-troubleshooting/),
[resolvectl --validate](https://www.freedesktop.org/software/systemd/man/latest/resolvectl.html)
et [resolved.conf DNSSEC](https://www.freedesktop.org/software/systemd/man/latest/resolved.conf.html).
La **correction persistante**, si justifiée
par une mesure comparée, doit être préparée
dans [ansible-workstation PR #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15),
avec rollback et validation du comportement
DNSSEC de pfSense avant toute réduction de
l'authentification.

## 23:XX CET — Validation DNSSEC privée isolée, expérience NTA ciblée

L'utilisateur a exécuté `just workstation-dnssec-test` :
**13/13 PASS**. Runtime `just workstation-dnssec-check`
deux cycles cohérents :

| Sonde | Cycle 1 | Cycle 2 |
|---|---|---|
| `private_validated` | TIMEOUT 4 s | TIMEOUT 4 s |
| `private_no_validation` | A_CONFIRMED 0 s | A_CONFIRMED 0 s |
| `public_validated` | A_CONFIRMED 0 s | A_CONFIRMED 0 s |
| `pfsense_signed_a` | ANSWER / RRSIG=yes / AD=yes | pareil |
| `pfsense_parent_ds` | ANSWER / RRSIG=yes / AD=yes | pareil |
| `pfsense_dnssec_bogus` | SERVFAIL | SERVFAIL |

La différence répétée entre validation normale et
`--validate=no` **sur DefectDojo privé** établit
le chemin DNSSEC de cette zone comme cause probable
des timeouts. Les signatures publiques DNSSEC reçues
via pfSense invalident l'hypothèse simple « Unbound
ne transmet aucune signature ». Les données n'attestent
pas encore que les enregistrements de la zone privée
sont effectivement dépourvus de RRSIG.

**Correction privilégiée :** *Negative Trust Anchor* (NTA)
`int.albandrieu.com` pour une zone privée non
signée sous domaine public, au lieu de `DNSSEC=no`
sur tous les noms. Source système :
[resolvectl nta](https://www.freedesktop.org/software/systemd/man/latest/resolvectl.html)
et [Negative Trust Anchors](https://www.freedesktop.org/software/systemd/man/latest/dnssec-trust-anchors.d.html).

### Étape locale, opt-in et réversible

```bash
cd ~/w/nabla-compose
git pull --ff-only
just workstation-dnssec-nta-test

# Inspection seulement ; exit 1 possible tant que DNSSEC privé expire
just workstation-dnssec-nta-check || true

# Action explicitement autorisée : NTA uniquement sur eno1.
# Refuse si le profil n'est pas Wired eno1, DNS != 172.17.0.1,
# zone route-only absente ou ancres NTA supplémentaires existantes.
just workstation-dnssec-nta-try

# Contrôler une requête validée sans --validate=no puis NSS/HTTPS.
resolvectl query -4 defectdojo.int.albandrieu.com
getent ahostsv4 defectdojo.int.albandrieu.com
resolvectl query -4 cloudflare.com
just workstation-nss-path
just defectdojo-workstation-dns-check
```

**Rollback explicite, seulement si l'ancre du lien était
initialement vide et qu'aucune autre ancre n'a été ajoutée :**

```bash
just workstation-dnssec-nta-rollback
```

Le retour en arrière efface la liste des NTA du lien
uniquement si elle contient exactement `int.albandrieu.com`.
Le script n'édite pas de fichier, ne modifie pas
`DNSSEC=yes`, ne change pas DoT, ne redémarre
ni pfSense ni `systemd-resolved`. Cette NTA **runtime
n'est pas persistante** ; aucun succès au runtime
n'est affirmé avant l'exécution opérateur.

### Persistance Ansible, distincte du test runtime

Propriétaire :
[ansible-workstation PR #15](https://github.com/AlbanAndrieu/ansible-workstation/pull/15),
`tasks/network_dnssec_nta.yml`.
Le rôle possède deux flags séparés désactivés par défaut :
`workstation_split_dns_persistent_nta_enabled=false`
et `workstation_split_dns_persistent_nta_remove_enabled=false`.
Il crée/supprime seulement le fichier
`/etc/dnssec-trust-anchors.d/90-nabla-int-albandrieu.negative`
avec le domaine `int.albandrieu.com`.
Attention, **le fichier est limité à la zone DNS mais
s'applique à tous les liens du poste**, contrairement
à la NTA runtime de `eno1`. Ne l'activer qu'après
validation de l'impact sur les VPN et autres interfaces.
Le handler redémarre `systemd-resolved` uniquement
si cette configuration change. Rollback explicite prévu.

**Nouveaux tests :** `tests/test_recover_split_dns_nta.py`
comporte **10 tests offline**, écrits mais non
exécutés à ce stade. Ansible ajoute un huitième
test de contrat NTA, également à recevoir.

**Risque non clos :** les nombreux messages
`DNSSEC validation failed: no-signature` sur
des domaines **publics** ne sont pas nécessairement
résolus par cette exception de zone privée.
Observer séparément DNSSEC public et les compteurs
`Bogus` sans remettre en cause les réponses
DNSSEC publiques déjà confirmées.

## Validation DONE

Confirmer que hide-location est désactivé, que le profil NM
persiste 172.17.0.1 et ~int.albandrieu.com après reapply puis
reboot, que getent et Chrome résolvent les services privés, et que
dig direct UDP **et** TCP n'expire pas. Si les timeouts UDP restent,
ouvrir un chantier pfSense/Unbound **séparé** de la reprise Chrome.
