# pfSense : retrait des cibles workstation 172.17.0.57 (14/11/2026)

## Contexte

Le relevé des journaux de la workstation du 14/11 (dépôt
ansible-workstation, `docs/stabilisation-workstation-truenas.md`, ligne 12)
attribue l'essentiel des `[UFW BLOCK]` à pfSense `172.17.0.1`. Rien n'écoute
plus sur ces ports de la workstation : les services sont partis sur TrueNAS.

Comptage sur 24 h (13/11 → 14/11, journalisation ufw limitée en débit,
le volume réel est plus élevé) :

| Port | Paquets journalisés | Remarque |
| --- | ---: | --- |
| UDP 1514 | 1 391 | syslog pfSense |
| TCP 3000 | 1 295 | health-checks HAProxy, toutes les secondes |
| TCP 9000 | 499 | health-check HAProxy |
| TCP 8081 | 349 | 13/11 de 14 h à 20 h seulement |

## État relevé le 14/11 (lecture seule)

Relevé par SSH (`ssh -p 9922 admin@172.17.0.1`) dans `/conf/config.xml`,
`/var/etc/haproxy/haproxy.cfg` et l'état runtime HAProxy. L'alias SSH
`pfsense` de `~/.ssh/config` ne résout pas depuis le LAN : utiliser l'IP.

| Objet pfSense | Cible | Service aujourd'hui | Décision |
| --- | --- | --- | --- |
| Syslog `remoteserver` | `172.17.0.57:1514` | Alloy TrueNAS `172.17.0.24:1514`, déjà en `remoteserver2` | Promouvoir TrueNAS en slot 1, retirer `.57` |
| HAProxy `ntopng` (`ntopng.albandrieu.com`, frontend WAN :8082) | `172.17.0.57:3000` | App TrueNAS `172.17.0.24:31080` | Serveur `inactive`, puis pool supprimé le 15/11 : pas de réexposition WAN du login ntopng |
| HAProxy `graylog` (`graylog.albandrieu.com`, :443 et :8082) | `172.17.0.57:9000` | App TrueNAS arrêtée volontairement (`planned`) | Serveur `inactive`, puis pool supprimé le 15/11 |
| HAProxy `albandrieu-apache-login-honeypot` (frontend `login`, WAN :3000) | `172.17.0.57:3000` | Aucun | Serveur `inactive` et frontend `login` désactivé |
| NAT rdr WAN :8081 « albandrieu nexus 8081 » et sa règle pass associée | `172.17.0.57:8081` | Nexus TrueNAS `172.17.0.24:8081`, servi par `nexus.int.albandrieu.com` | Supprimer : la politique d'ingress bloque l'accès direct à l'origine Nexus |

Le `:8081` n'est pas un health-check HAProxy : le pool `nexus` n'est
référencé par aucun frontend. Les paquets venaient de la redirection NAT,
réfléchie depuis le LAN (source réécrite en `172.17.0.1`).

Les backends `ntopng`, `graylog` et `albandrieu-apache-login-honeypot`
répondent déjà 503 : la décision ne retire aucun accès fonctionnel.

Les pools `ntopng` et `graylog` sont supprimés entiers, pas redirigés vers
TrueNAS : `172.17.0.24:3000` est Langfuse, `:9000` ClickHouse, et ntopng
écoute sur `:31080`. Le script ne les supprime que si tous leurs serveurs
sont `inactive` et qu'aucun frontend ne les utilise ; sinon il s'arrête en
`ERROR` sans rien écrire.

## Hors périmètre

- Pools `nexus` (`.57:8081`) et `vault` (`.57:8200`) : référencés par aucun
  frontend, donc ni générés ni sondés. Périmés mais inertes.

## Ajout du 15/11 : Apache de la workstation et secours Homarr

Décision opérateur du 15/11 : l'Apache de la workstation (`:8082`) n'est plus
publié que par le tunnel Cloudflare de la workstation, derrière Access
(`famp-albandrieu.albandrieu.com`, `terraform/cloudflare`). Le script passe donc
`inactive` les serveurs `.57:8082` des pools `albandrieu-apache`, `nabla-index`
et `prod_front` ; les hôtes `apache`, `account` et `famp` répondent 503 sur
HAProxy. Apache écoute sur `127.0.0.1:8082` (ansible-workstation,
`files/etc/apache2/ports.conf`), et la règle ufw LAN du 8082 disparaît.

`prod_back` (backend par défaut de `Web_HTTPS` et `freenas`) reçoit Homarr
(`172.17.0.24:30100`) en serveur `backup` quand Heimdall est DOWN. Sa sonde
passe de `/tag/nabla` à `/` : Homarr répond 404 sur `/tag/nabla`, donc un
backup sondé là ne servirait jamais.

```bash
ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/prod-back-homarr-fallback.php
```

Ordre d'application : `tofu apply` (Access + origine `127.0.0.1:8082`),
puis les deux scripts pfSense en `apply`, puis le playbook
`stabilize-workstation` (écoute sur la boucle locale).

**APPLIQUÉ le 15/11 vers 23:05** : `retire-workstation-targets.php` (serveurs
`.57` de `prod_front`, `nabla-index`, `albandrieu-apache`, `nexus`, `vault`
passés `inactive`), puis `prune-dead-haproxy-routes.php` (13 règles
`use_backend` vers ces pools vides et 24 ACL inutilisées supprimées).
`--check-posture` : `haproxy_workstation_servers=none`, `drift=0`. Effet
constaté : `apache`, `account`, `redis` et `traefik` (en-tête `Host` vers
`82.66.4.247`) tombent désormais sur le backend par défaut `prod_back`
(login Heimdall, 302), et les chemins `signature`/`logo` servis par
`prod_front` répondent 503. Le frontend `Web_HTTPS-8082` garde `nabla-index`,
vide, comme backend par défaut. Secours Homarr et `tofu apply` non appliqués.

## Procédure

### 1. Syslog

Clé dédiée : Vaultwarden `nabla/prod/pfsense-observability`, à charger dans
`PFSENSE_OBSERVABILITY_API_KEY` sans l'afficher. Lever le mode lecture
seule global de pfREST le temps du PATCH, puis le rétablir.

```bash
scripts/observability/configure-pfsense-syslog.sh --plan
```

```bash
scripts/observability/configure-pfsense-syslog.sh --apply
```

Le script reconnaît la disposition `remoteserver=.57` / `remoteserver2=Alloy`,
promeut Alloy en `remoteserver` et vide `remoteserver2`.

### 2. HAProxy et NAT

`scripts/pfsense/retire-workstation-targets.php` s'exécute sur pfSense.
`check` n'écrit rien. `apply` refuse d'écrire si l'un des objets attendus
manque, sauvegarde la configuration (une entrée dans l'historique
`Diagnostics > Backup & Restore > Config History`), recharge HAProxy puis
le filtre.

```bash
ssh -p 9922 admin@172.17.0.1 "php -- check" < scripts/pfsense/retire-workstation-targets.php
```

```bash
ssh -p 9922 admin@172.17.0.1 "php -- apply" < scripts/pfsense/retire-workstation-targets.php
```

Un second `check` doit n'afficher que des lignes `OK:`.

## Vérification

Sur pfSense :

```bash
ssh -p 9922 admin@172.17.0.1 "grep -n 172.17.0.57 /var/etc/haproxy/haproxy.cfg /var/etc/syslog.d/pfSense.conf"
```

Seules les lignes `:8082` doivent rester.

`scripts/pfsense/diagnose-recover.sh --check` échoue (ligne rouge
`pfsense_remote_syslog_legacy_workstation=present`) tant que `.57:1514`
reste configuré. Le 15/11, le repli sur l'environnement de boot
`default_clone` l'avait réintroduit en `remoteserver`.

Sur la workstation, après dix minutes :

```bash
journalctl -k --since -10min | grep -c 'UFW BLOCK.*SRC=172.17.0.1 '
```

## Retour arrière

Restaurer l'entrée précédente de `Diagnostics > Backup & Restore >
Config History`, ou réappliquer les valeurs du tableau ci-dessus dans
l'UI HAProxy et NAT.
